import os, json, requests, pandas as pd
import panel as pn
import hvplot.pandas
from datetime import datetime
from math import pi
from io import BytesIO

pn.extension("tabulator", sizing_mode="stretch_width")
API_URL = os.getenv("BLOCKCHAIN_API_URL", "http://127.0.0.1:3000/api/v1")
API_KEY = os.getenv("API_KEY", "dev-change-this-key")
HEADERS = {"x-api-key": API_KEY}

def api_get(path):
    try:
        r = requests.get(API_URL + path, headers=HEADERS, timeout=4)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_post(path, payload):
    try:
        r = requests.post(API_URL + path, json=payload, headers=HEADERS, timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def metric(title, value, note=""):
    return pn.Card(pn.pane.Markdown(f"### {value}\n**{title}**\n\n<small>{note}</small>"),
                   styles={"background": "#ffffff", "border": "1px solid #e5e7eb"},
                   sizing_mode="stretch_width")

status = pn.pane.Alert("Connecting to blockchain API…", alert_type="info")
kpi_row = pn.Row(sizing_mode="stretch_width")
chain_table = pn.widgets.Tabulator(pd.DataFrame(), pagination="local", page_size=10, height=360)
timber_table = pn.widgets.Tabulator(pd.DataFrame(), pagination="local", page_size=10, height=360)
history_table = pn.widgets.Tabulator(pd.DataFrame(), pagination="local", page_size=10, height=300)
explorer = pn.Column()
verify_result = pn.pane.Alert("Run ledger verification to inspect chain integrity.", alert_type="light")
chart_area = pn.Column()

def refresh_dashboard():
    health = api_get("/health")
    chain = api_get("/chain")
    timbers = api_get("/timber")
    if "error" in health:
        status.object = f"API unavailable: {health['error']}"
        status.alert_type = "danger"
        return
    status.object = f"Connected · {health.get('service','Forest Traceability Blockchain')} · API {health.get('version','')}"
    status.alert_type = "success"
    blocks = chain.get("chain", []) if isinstance(chain, dict) else []
    items = timbers.get("timber", []) if isinstance(timbers, dict) else []
    pending = chain.get("pendingTransactions", 0) if isinstance(chain, dict) else 0
    kpi_row.objects = [
        metric("Total blocks", len(blocks), "Persisted ledger"),
        metric("Registered timber", len(items), "Unique grume IDs"),
        metric("Pending transactions", pending, "Awaiting block mining"),
        metric("Chain status", "Operational", "API connected")
    ]
    chain_table.value = pd.DataFrame([{
        "Index": b.get("index"), "Timestamp": b.get("timestamp"),
        "Transactions": len(b.get("transactions", [])),
        "Previous hash": str(b.get("previousHash",""))[:18] + "…",
        "Hash": str(b.get("hash",""))[:18] + "…",
        "Nonce": b.get("nonce")
    } for b in blocks])
    timber_table.value = pd.DataFrame(items)
    if blocks:
        df = pd.DataFrame([{"Block": b.get("index"), "Transactions": len(b.get("transactions", []))} for b in blocks])
        chart_area.objects = [df.hvplot.bar(x="Block", y="Transactions", height=280,
                           title="Transactions per block", color="#16866f",
                           ylabel="Transactions", xlabel="Block", rot=0)]
    else:
        chart_area.objects = [pn.pane.Markdown("No blocks yet. Register timber and add events to begin.")]

refresh_btn = pn.widgets.Button(name="Refresh dashboard", button_type="primary", icon="refresh")
refresh_btn.on_click(lambda event: refresh_dashboard())

# Timber registration
grume_id = pn.widgets.TextInput(name="Unique timber / grume ID", placeholder="e.g. RCA-LOB-2026-0001")
species = pn.widgets.Select(name="Timber species", options=["Akon", "Sapelli", "Ayous", "Iroko", "Sipo", "Fraké", "Other"], value="Sapelli")

# Volume is calculated from measured diameter and length:
# V = pi * (D / 2)^2 * L, with diameter converted from cm to metres.
diameter_cm = pn.widgets.FloatInput(name="Diameter (cm)", value=60.0, start=0.1, step=1)
length_m = pn.widgets.FloatInput(name="Length (m)", value=5.0, start=0.1, step=0.1)
volume = pn.widgets.FloatInput(name="Calculated volume (m³)", value=1.414, start=0.001, step=0.001, disabled=True)
def update_volume(event=None):
    d = float(diameter_cm.value or 0)
    length = float(length_m.value or 0)
    calculated = pi * (d / 200.0) ** 2 * length
    volume.value = round(calculated, 3) if calculated > 0 else 0.0
diameter_cm.param.watch(update_volume, "value")
length_m.param.watch(update_volume, "value")
update_volume()

harvest_date = pn.widgets.DatePicker(name="Harvest date", value=datetime.now().date())
origin = pn.widgets.Select(name="Forest origin / concession", options=[
    "Lobaye", "Berberati", "Sangha-Mbaéré", "Mambéré-Kadéï",
    "Ombella-M'Poko", "Nana-Mambéré", "Other"
], value="Lobaye")
gps = pn.widgets.TextInput(name="GPS coordinates", placeholder="Click 'Get my location' to capture latitude, longitude")
gps_btn = pn.widgets.Button(name="Get my location", button_type="primary", icon="map-pin")
gps_btn.js_on_click(args={"gps": gps}, code="""
if (!navigator.geolocation) {
    gps.value = "Geolocation is not supported by this browser";
} else {
    gps.value = "Getting location…";
    navigator.geolocation.getCurrentPosition(
        function(position) {
            gps.value = position.coords.latitude.toFixed(6) + ", " +
                        position.coords.longitude.toFixed(6);
        },
        function(error) {
            const messages = {
                1: "Location permission denied",
                2: "Location unavailable",
                3: "Location request timed out"
            };
            gps.value = messages[error.code] || error.message;
        },
        {enableHighAccuracy: true, timeout: 15000, maximumAge: 0}
    );
}
""")
gps_note = pn.pane.Markdown(
    "<small>GPS requires browser permission. It works on localhost or on a secure HTTPS website.</small>"
)
register_msg = pn.pane.Alert("", visible=False)
def register_timber(event):
    if not grume_id.value.strip():
        result = {"error": "Please enter a unique timber / grume ID."}
    elif diameter_cm.value <= 0 or length_m.value <= 0 or volume.value <= 0:
        result = {"error": "Diameter and length must be greater than zero."}
    elif not harvest_date.value:
        result = {"error": "Please select the harvest date."}
    else:
        result = api_post("/timber", {"grumeId": grume_id.value.strip(), "species": species.value,
            "volumeM3": volume.value, "diameterCm": diameter_cm.value, "lengthM": length_m.value,
            "harvestDate": harvest_date.value.strftime("%d-%m-%Y"),
            "origin": origin.value, "gps": gps.value})
    register_msg.object = json.dumps(result, ensure_ascii=False, indent=2)
    register_msg.alert_type = "success" if "error" not in result else "danger"
    register_msg.visible = True
    refresh_dashboard()
register_btn = pn.widgets.Button(name="Register timber", button_type="success")
register_btn.on_click(register_timber)


# Excel import/export for timber registration
excel_file = pn.widgets.FileInput(
    name="Choose Excel file (.xlsx)",
    accept=".xlsx,.xls",
    multiple=False
)
excel_import_msg = pn.pane.Alert("", visible=False)
import_excel_btn = pn.widgets.Button(name="Import timber from Excel", button_type="primary", icon="upload")
export_excel_btn = pn.widgets.FileDownload(
    name="Export registered timber to Excel",
    callback=lambda: export_registered_timber_excel(),
    filename="registered_timber.xlsx",
    button_type="success"
)
template_excel_btn = pn.widgets.FileDownload(
    name="Download Excel template",
    callback=lambda: create_timber_excel_template(),
    filename="timber_registration_template.xlsx",
    button_type="light"
)

def _excel_cell_text(value):
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d-%m-%Y")
    return str(value).strip()

def _excel_date(value):
    if pd.isna(value) or value == "":
        return ""
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%d-%m-%Y")
    parsed = pd.to_datetime(str(value), dayfirst=True, errors="coerce")
    return parsed.strftime("%d-%m-%Y") if not pd.isna(parsed) else str(value).strip()

def import_timber_excel(event):
    if not excel_file.value:
        excel_import_msg.object = "Please choose an Excel file first."
        excel_import_msg.alert_type = "warning"
        excel_import_msg.visible = True
        return

    try:
        workbook = pd.read_excel(BytesIO(excel_file.value))
        # Normalize headers while retaining the expected camelCase names.
        normalized = {str(col).strip().lower().replace(" ", "").replace("_", ""): col
                      for col in workbook.columns}
        def get_column(*names):
            for name in names:
                key = name.lower().replace(" ", "").replace("_", "")
                if key in normalized:
                    return normalized[key]
            return None

        id_col = get_column("grumeId", "timberId", "id")
        species_col = get_column("species", "timberSpecies")
        volume_col = get_column("volumeM3", "volume")
        diameter_col = get_column("diameterCm", "diameter")
        length_col = get_column("lengthM", "length")
        date_col = get_column("harvestDate", "date")
        origin_col = get_column("origin", "forestOrigin", "concession")
        gps_col = get_column("gps", "coordinates", "gpsCoordinates")

        if id_col is None or species_col is None:
            raise ValueError("The Excel file must contain at least 'grumeId' and 'species' columns.")
        if volume_col is None and (diameter_col is None or length_col is None):
            raise ValueError("Provide either 'volumeM3' or both 'diameterCm' and 'lengthM' columns.")

        success_count, errors = 0, []
        for row_number, row in workbook.iterrows():
            excel_row = row_number + 2
            grume_value = _excel_cell_text(row[id_col])
            species_value = _excel_cell_text(row[species_col])
            if not grume_value or not species_value:
                errors.append(f"Row {excel_row}: grumeId and species are required.")
                continue

            try:
                if volume_col is not None and not pd.isna(row[volume_col]) and str(row[volume_col]).strip():
                    volume_value = float(row[volume_col])
                else:
                    diameter_value = float(row[diameter_col])
                    length_value = float(row[length_col])
                    volume_value = math.pi * (diameter_value / 200.0) ** 2 * length_value

                if volume_value <= 0:
                    raise ValueError("volume must be greater than zero")

                diameter_value = None
                length_value = None
                if diameter_col is not None and not pd.isna(row[diameter_col]):
                    diameter_value = float(row[diameter_col])
                if length_col is not None and not pd.isna(row[length_col]):
                    length_value = float(row[length_col])

                payload = {
                    "grumeId": grume_value,
                    "species": species_value,
                    "volumeM3": round(volume_value, 3),
                    "diameterCm": diameter_value,
                    "lengthM": length_value,
                    "harvestDate": _excel_date(row[date_col]) if date_col is not None else "",
                    "origin": _excel_cell_text(row[origin_col]) if origin_col is not None else "",
                    "gps": _excel_cell_text(row[gps_col]) if gps_col is not None else ""
                }
                result = api_post("/timber", payload)
                if "error" in result:
                    errors.append(f"Row {excel_row} ({grume_value}): {result['error']}")
                else:
                    success_count += 1
            except Exception as row_error:
                errors.append(f"Row {excel_row}: {row_error}")

        summary = f"Excel import completed. Successfully registered: {success_count}. Errors: {len(errors)}."
        if errors:
            summary += "\n\n" + "\n".join(errors[:15])
            if len(errors) > 15:
                summary += f"\n... and {len(errors) - 15} more error(s)."
        excel_import_msg.object = summary
        excel_import_msg.alert_type = "success" if not errors else ("warning" if success_count else "danger")
        refresh_dashboard()
    except Exception as exc:
        excel_import_msg.object = f"Could not read the Excel file: {exc}"
        excel_import_msg.alert_type = "danger"
    excel_import_msg.visible = True

import_excel_btn.on_click(import_timber_excel)

def create_timber_excel_template():
    columns = ["grumeId", "species", "diameterCm", "lengthM", "volumeM3",
               "harvestDate", "origin", "gps"]
    example = [{
        "grumeId": "RCA-LOB-2026-0001",
        "species": "Sapelli",
        "diameterCm": 60,
        "lengthM": 5,
        "volumeM3": "",
        "harvestDate": datetime.now().strftime("%d-%m-%Y"),
        "origin": "Lobaye",
        "gps": "4.123456, 18.123456"
    }]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(example, columns=columns).to_excel(writer, index=False, sheet_name="Timber")
        pd.DataFrame({
            "Column": columns,
            "Description": [
                "Unique timber / grume identifier (required)",
                "Species name (required)",
                "Log diameter in centimetres",
                "Log length in metres",
                "Volume in cubic metres; optional if diameterCm and lengthM are supplied",
                "Harvest date (dd-mm-yyyy recommended)",
                "Forest origin / concession",
                "Latitude, longitude"
            ]
        }).to_excel(writer, index=False, sheet_name="Instructions")
    output.seek(0)
    return output

def export_registered_timber_excel():
    response = api_get("/timber")
    records = response.get("timber", []) if isinstance(response, dict) else []
    if not records:
        records = [{
            "grumeId": "", "species": "", "diameterCm": "", "lengthM": "",
            "volumeM3": "", "harvestDate": "", "origin": "", "gps": ""
        }]
    frame = pd.DataFrame(records)
    preferred = ["grumeId", "species", "diameterCm", "lengthM", "volumeM3",
                 "harvestDate", "origin", "gps", "registeredAt"]
    frame = frame[[col for col in preferred if col in frame.columns] +
                  [col for col in frame.columns if col not in preferred]]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Registered Timber")
    output.seek(0)
    return output

# Event entry
event_grume = pn.widgets.TextInput(name="Grume ID")
event_type = pn.widgets.Select(name="Traceability event", options=[
    "HARVEST", "FOREST_GATE", "TRANSPORT", "SAWMILL_INTAKE",
    "PROCESSING", "WAREHOUSE", "SALE", "EXPORT"])
actor = pn.widgets.TextInput(name="Responsible operator / organization")
location = pn.widgets.TextInput(name="Location")
event_notes = pn.widgets.TextAreaInput(name="Notes", height=100)
event_msg = pn.pane.Alert("", visible=False)
def add_event(event):
    result = api_post("/events", {"grumeId": event_grume.value.strip(), "eventType": event_type.value,
        "actor": actor.value, "location": location.value, "notes": event_notes.value})
    event_msg.object = json.dumps(result, ensure_ascii=False, indent=2)
    event_msg.alert_type = "success" if "error" not in result else "danger"
    event_msg.visible = True
    refresh_dashboard()
event_btn = pn.widgets.Button(name="Add blockchain transaction", button_type="primary")
event_btn.on_click(add_event)

# History
history_id = pn.widgets.TextInput(name="Grume ID", placeholder="Enter a registered ID")
history_msg = pn.pane.Alert("", visible=False)
def load_history(event):
    result = api_get("/timber/" + requests.utils.quote(history_id.value.strip(), safe="") + "/history")
    if "error" in result:
        history_msg.object = result["error"]; history_msg.alert_type = "danger"
    else:
        history_msg.object = f"History loaded for {history_id.value}"
        history_msg.alert_type = "success"
        history_table.value = pd.DataFrame(result.get("history", []))
    history_msg.visible = True
history_btn = pn.widgets.Button(name="Load traceability history", button_type="primary")
history_btn.on_click(load_history)

# Verification and explorer
def verify(event):
    result = api_get("/ledger/verify")
    valid = result.get("valid", False)
    verify_result.object = json.dumps(result, ensure_ascii=False, indent=2)
    verify_result.alert_type = "success" if valid else "danger"
verify_btn = pn.widgets.Button(name="Verify entire blockchain", button_type="warning")
verify_btn.on_click(verify)
def load_explorer(event):
    result = api_get("/chain")
    blocks = result.get("chain", [])
    explorer.objects = [pn.pane.JSON(b, depth=4, name=f"Block {b.get('index')}") for b in blocks]
explorer_btn = pn.widgets.Button(name="Load blocks", button_type="primary")
explorer_btn.on_click(load_explorer)

# Arena connection settings / guidance
arena_url = pn.widgets.TextInput(name="Arena API base URL", placeholder="https://arena.example.org/api")
arena_token = pn.widgets.PasswordInput(name="Arena access token")
arena_note = pn.pane.Markdown(
    "**Integration note:** Configure your Arena API endpoint and authentication in the backend `.env` file. "
    "This interface does not send credentials to Arena until a dedicated Arena adapter is configured."
)

header = pn.Column(
    pn.Row(pn.pane.Markdown("# 🌳 Forest Traceability Blockchain", styles={"color":"white"}),
           pn.Spacer(), refresh_btn, sizing_mode="stretch_width"),
    pn.pane.Markdown("**Timber legality · Chain of custody · Verifiable digital records**",
                     styles={"color":"#cbd5e1"}),
    styles={"background":"#102b26","padding":"18px","border-radius":"12px"}
)

dashboard = pn.Column(status, kpi_row, chart_area, pn.pane.Markdown("### Latest blockchain blocks"), chain_table,
                      pn.pane.Markdown("### Registered timber"), timber_table)
register_view = pn.Column("## Register timber", "Create a unique timber identity before recording its chain-of-custody events.",
                          grume_id, species,
                          pn.pane.Markdown("### Timber dimensions and automatic volume calculation"),
                          pn.Row(diameter_cm, length_m), volume,
                          pn.Row(harvest_date, origin), pn.pane.Markdown("### GPS geolocation"),
                          pn.Row(gps, gps_btn), gps_note, register_btn, register_msg,
                          pn.pane.Markdown("---"),
                          pn.pane.Markdown("### Import timber records from Excel"),
                          pn.pane.Markdown(
                              "Choose an Excel workbook to register multiple timber records. "
                              "Use the template to prepare the required columns."
                          ),
                          excel_file, pn.Row(import_excel_btn, template_excel_btn),
                          excel_import_msg,
                          pn.pane.Markdown("### Export registered timber"),
                          export_excel_btn)
event_view = pn.Column("## Record a traceability event", "Each event is submitted as a transaction and included in a mined block.",
                       event_grume, event_type, actor, location, event_notes, event_btn, event_msg)
history_view = pn.Column("## Timber traceability history", history_id, history_btn, history_msg, history_table)
ledger_view = pn.Column("## Blockchain explorer", verify_btn, verify_result, pn.pane.Markdown("---"),
                        explorer_btn, explorer)
arena_view = pn.Column("## OpenForis Arena integration", arena_note, arena_url, arena_token,
                       pn.pane.Markdown("The backend exposes a REST API suitable for an Arena integration adapter."))

tabs = pn.Tabs(("Dashboard", dashboard), ("Register timber", register_view),
               ("Record event", event_view), ("Traceability", history_view),
               ("Blockchain explorer", ledger_view), ("Arena integration", arena_view),
               dynamic=True, sizing_mode="stretch_both")
template = pn.template.FastListTemplate(
    title="Forest Traceability",
    sidebar=[pn.pane.Markdown("## Navigation"), pn.pane.Markdown(
        "Use the tabs to register timber, record events, inspect provenance and verify ledger integrity."),
        pn.pane.Markdown("---"), pn.pane.Markdown("**Technology**\n\nPython Panel\n\nNode.js API\n\nSHA-256 blockchain")],
    main=[header, tabs],
    accent_base_color="#16866f", header_background="#102b26",
    theme="default"
)
refresh_dashboard()
template.servable()
