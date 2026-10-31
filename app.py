import os, json, requests, pandas as pd
import panel as pn
import hvplot.pandas
from datetime import datetime
from math import pi
from io import BytesIO

pn.extension("tabulator", sizing_mode="stretch_width")
API_URL = os.getenv("BLOCKCHAIN_API_URL", "http://127.0.0.1:3000/api/v1")
API_KEY = os.getenv("API_KEY", "")
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
    refresh_geo_data(items)
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
origin = pn.widgets.Select(name="Forest zone / concession", options=[
    "Lobaye", "Berberati", "Sangha-Mbaéré", "Mambéré-Kadéï",
    "Ombella-M'Poko", "Nana-Mambéré", "Other"
], value="Lobaye")

gps = pn.widgets.TextInput(
    name="GPS coordinates (latitude, longitude)",
    placeholder="e.g. 4.123456, 18.123456"
)
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
    "<small>GPS capture requires browser permission and localhost or HTTPS.</small>"
)
# Timber registration
register_msg = pn.pane.Alert("", visible=False)

def register_timber(event):
    if not grume_id.value.strip():
        result = {"error": "Please enter a unique timber / grume ID."}
    elif diameter_cm.value <= 0 or length_m.value <= 0 or volume.value <= 0:
        result = {"error": "Diameter and length must be greater than zero."}
    elif not harvest_date.value:
        result = {"error": "Please select the harvest date."}
    else:
        result = api_post("/timber", {
            "grumeId": grume_id.value.strip(),
            "species": species.value,
            "volumeM3": volume.value,
            "diameterCm": diameter_cm.value,
            "lengthM": length_m.value,
            "harvestDate": harvest_date.value.strftime("%d-%m-%Y"),
            "origin": origin.value,
            "gps": gps.value.strip()
        })

    register_msg.object = json.dumps(result, ensure_ascii=False, indent=2)
    register_msg.alert_type = "success" if "error" not in result else "danger"
    register_msg.visible = True

    if "error" not in result:
        refresh_dashboard()

register_btn = pn.widgets.Button(name="Register timber", button_type="success")
register_btn.on_click(register_timber)


# Geographic map workspace
# Map markers are colored by forest origin; the Essence dropdown filters species.
species_filter = pn.widgets.Select(
    name="Essence",
    options=["All species"],
    value="All species",
    sizing_mode="stretch_width"
)
geo_status = pn.pane.Alert(
    "GPS coordinates will appear here when registered timber records contain valid positions.",
    alert_type="info"
)
geo_map = pn.pane.HTML(
    "<div style='padding:24px;text-align:center;color:#64748b;'>No GPS data available yet.</div>",
    height=620,
    sizing_mode="stretch_width"
)
geo_summary = pn.Row(sizing_mode="stretch_width")
geo_records_table = pn.widgets.Tabulator(
    pd.DataFrame(columns=[
        "Grume ID", "Species", "Origine", "Latitude", "Longitude", "Coordinates"
    ]),
    pagination="local",
    page_size=12,
    height=340,
    sizing_mode="stretch_width"
)

def _get_timber_records():
    response = api_get("/timber")
    if isinstance(response, dict) and "error" not in response:
        records = response.get("timber", [])
        return records if isinstance(records, list) else []
    return []

def _record_coordinates(record):
    gps_value = record.get("gps") or record.get("coordinates") or record.get("gpsCoordinates")
    lat_value = record.get("latitude", record.get("lat"))
    lon_value = record.get("longitude", record.get("lon", record.get("lng")))
    try:
        if lat_value not in (None, "") and lon_value not in (None, ""):
            lat, lon = float(lat_value), float(lon_value)
        elif isinstance(gps_value, dict):
            lat = float(gps_value.get("latitude", gps_value.get("lat")))
            lon = float(gps_value.get("longitude", gps_value.get("lon", gps_value.get("lng"))))
        elif isinstance(gps_value, (list, tuple)) and len(gps_value) >= 2:
            lat, lon = float(gps_value[0]), float(gps_value[1])
        else:
            parts = [p.strip() for p in str(gps_value or "").replace(";", ",").split(",")]
            if len(parts) < 2:
                return None
            lat, lon = float(parts[0]), float(parts[1])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 6), round(lon, 6)
    except (TypeError, ValueError):
        return None
    return None

def refresh_geo_data(records=None):
    if records is None:
        records = _get_timber_records()
    species_values = sorted({
        str(record.get("species", "")).strip()
        for record in records if str(record.get("species", "")).strip()
    })
    options = ["All species"] + species_values
    current = species_filter.value
    species_filter.options = options
    species_filter.value = current if current in options else "All species"
    _render_geo_map(species_filter.value, records)

def _render_geo_map(selected_species="All species", records=None):
    import folium
    from branca.element import Element

    if records is None:
        records = _get_timber_records()

    valid_rows = []
    missing_count = 0
    for record in records:
        coords = _record_coordinates(record)
        if coords is None:
            missing_count += 1
            continue
        lat, lon = coords
        valid_rows.append({
            "Grume ID": str(record.get("grumeId", record.get("timberId", "Timber"))),
            "Species": str(record.get("species", "Unknown")),
            "Origine": str(record.get("origin", "Unspecified") or "Unspecified"),
            "Latitude": lat,
            "Longitude": lon,
            "Coordinates": f"{lat:.6f}, {lon:.6f}",
            "Volume (m³)": record.get("volumeM3", "")
        })

    frame = pd.DataFrame(valid_rows)
    if selected_species != "All species" and not frame.empty:
        frame = frame[frame["Species"] == selected_species]

    origins_count = frame["Origine"].nunique() if not frame.empty else 0
    geo_summary.objects = [
        metric("GPS timber records", len(frame), "After Essence filter"),
        metric("Forest origins", origins_count, "Shown in map legend"),
        metric("Missing GPS", missing_count, "Records without valid coordinates")
    ]

    columns = ["Grume ID", "Species", "Origine", "Latitude", "Longitude", "Coordinates"]
    geo_records_table.value = frame[columns] if not frame.empty else pd.DataFrame(columns=columns)

    if frame.empty:
        geo_map.object = (
            "<div style='padding:28px;text-align:center;color:#64748b;"
            "border:1px solid #e2e8f0;border-radius:8px;'>"
            "No valid GPS points match this Essence filter. Add GPS coordinates to timber records."
            "</div>"
        )
        geo_status.object = "No GPS points to display for the selected Essence."
        geo_status.alert_type = "warning"
        return

    # Aggregate records by forest origin and essence. Each bubble represents
    # the total number of registered grumes for that Essence in that Origine.
    # Its position is the average GPS location of those records.
    bubble_data = (
        frame.groupby(["Origine", "Species"], dropna=False)
        .agg(
            **{
                "Total grumes": ("Grume ID", "count"),
                "Latitude": ("Latitude", "mean"),
                "Longitude": ("Longitude", "mean"),
                "Total volume (m³)": ("Volume (m³)", lambda values: pd.to_numeric(values, errors="coerce").fillna(0).sum()),
                "Grume IDs": ("Grume ID", lambda values: ", ".join(values.astype(str).tolist()))
            }
        )
        .reset_index()
    )

    center = [float(frame["Latitude"].mean()), float(frame["Longitude"].mean())]
    zoom = 7 if len(frame) > 1 else 11

    map_view = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True
    )

    # Bubble AREA is proportional to the total number of grumes in each
    # Origine/Essence group, not to timber volume.
    max_count = int(bubble_data["Total grumes"].max()) if not bubble_data.empty else 0
    min_bubble_radius = 7
    max_bubble_radius = 38

    # Stable, distinct marker colors by Origine (also used in the legend).
    palette = [
        "#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed",
        "#0891b2", "#be185d", "#4d7c0f", "#9333ea", "#475569",
        "#ea580c", "#0f766e", "#a21caf", "#65a30d", "#1d4ed8"
    ]
    origins = sorted(bubble_data["Origine"].unique().tolist())
    origin_colors = {name: palette[i % len(palette)] for i, name in enumerate(origins)}

    for _, row in bubble_data.iterrows():
        color = origin_colors[row["Origine"]]
        count_value = int(row["Total grumes"])
        total_volume = float(row["Total volume (m³)"] or 0)

        popup_html = (
            f"<b>Origine:</b> {row['Origine']}<br>"
            f"<b>Essence:</b> {row['Species']}<br>"
            f"<b>Nombre total de grumes:</b> {count_value}<br>"
            f"<b>Volume total:</b> {total_volume:,.3f} m³<br>"
            f"<b>Grume IDs:</b> {row['Grume IDs']}"
        )

        # Proportional-symbol map: bubble AREA is proportional to the
        # number of grumes in this Origine/Essence group.
        if max_count > 0 and count_value > 0:
            marker_radius = min_bubble_radius + (
                (max_bubble_radius - min_bubble_radius)
                * (count_value / max_count) ** 0.5
            )
        else:
            marker_radius = min_bubble_radius

        folium.CircleMarker(
            location=[row["Latitude"], row["Longitude"]],
            radius=marker_radius,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.72,
            tooltip=(
                f"{row['Origine']} · {row['Species']} · "
                f"Total grumes: {count_value}"
            ),
            popup=folium.Popup(popup_html, max_width=360)
        ).add_to(map_view)

    legend_rows = "".join(
        f"<div style='display:flex;align-items:center;margin:4px 0;'>"
        f"<span style='display:inline-block;width:12px;height:12px;border-radius:50%;"
        f"background:{origin_colors[name]};margin-right:8px;'></span>"
        f"<span>{name}</span></div>"
        for name in origins
    )
    legend_html = (
        "<div style='position:fixed;bottom:28px;right:18px;z-index:9999;"
        "background:white;border:1px solid #cbd5e1;border-radius:6px;"
        "padding:10px 12px;max-height:220px;overflow-y:auto;"
        "box-shadow:0 1px 5px rgba(0,0,0,.25);font-size:13px;'>"
        "<div style='font-weight:700;margin-bottom:6px;'>Origine</div>"
        f"{legend_rows}</div>"
    )
    map_view.get_root().html.add_child(Element(legend_html))

    # Folium's representation is an iframe with an embedded map document,
    # which Panel can display inside its HTML pane.
    geo_map.object = map_view.get_root()._repr_html_()
    geo_status.object = (
        f"Displaying **{len(frame)}** timber GPS point(s). "
        "Marker colors and the map legend represent **Origine**; "
        "bubble size represents the **total number of grumes** for each Essence and Origine; "
        "the **Essence** dropdown filters the displayed groups."
    )
    geo_status.alert_type = "success"

def _species_changed(event):
    _render_geo_map(event.new)

species_filter.param.watch(_species_changed, "value")

geo_refresh_btn = pn.widgets.Button(
    name="Refresh GPS data",
    button_type="primary",
    icon="refresh"
)

def refresh_geo_from_system(event=None):
    records = _get_timber_records()
    refresh_geo_data(records)
    if not records:
        geo_status.object = "No timber records were returned by the blockchain API."
        geo_status.alert_type = "warning"

geo_refresh_btn.on_click(refresh_geo_from_system)

geo_view = pn.Column(
    "## Timber geolocation – Interactive map",
    "Each bubble represents the total number of grumes for an Essence within an Origine. Bubble size represents the grume count; the **Origine** legend identifies the forest origin by color. Use the **Essence** dropdown to filter species.",
    pn.Row(species_filter, geo_refresh_btn, sizing_mode="stretch_width"),
    geo_status,
    geo_summary,
    geo_map,
    pn.pane.Markdown("### GPS coordinates by timber record"),
    geo_records_table,
    sizing_mode="stretch_width"
)

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
                    volume_value = pi * (diameter_value / 200.0) ** 2 * length_value

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
                "Forest zone / concession",
                "GPS coordinates as latitude, longitude"
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

# Statistics graph dashboard (reads data/forest-blockchain.json)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BLOCKCHAIN_JSON_PATH = os.path.join(APP_DIR, "data", "forest-blockchain.json")

def load_statistics_records():
    """Read timber registrations from the project's data/forest-forest-blockchain.json file."""
    json_path = BLOCKCHAIN_JSON_PATH

    if not os.path.isfile(json_path):
        return pd.DataFrame(), (
            "Blockchain data file was not found. Expected location: "
            f"{json_path}. Create a 'data' folder beside app.py and place "
            "blockchain.json inside it."
        )

    try:
        with open(json_path, "r", encoding="utf-8") as json_file:
            payload = json.load(json_file)

        rows = []

        # Standard blockchain export: registrations are stored in block transactions.
        chain_data = payload.get("chain", []) if isinstance(payload, dict) else []
        for block in chain_data:
            for transaction in block.get("transactions", []):
                if transaction.get("type") != "TIMBER_REGISTERED":
                    continue
                record = transaction.get("data", {}) or {}
                rows.append({
                    "Grume ID": record.get("grumeId", transaction.get("grumeId", "")),
                    "Essence": record.get("species", "Unknown") or "Unknown",
                    "Origine": record.get("origin", "Unspecified") or "Unspecified",
                    "Volume (m³)": record.get("volumeM3"),
                    "Diamètre (cm)": record.get("diameterCm"),
                    "Longueur (m)": record.get("lengthM"),
                    "Date de récolte": record.get("harvestDate", ""),
                    "Date d'enregistrement": record.get("registeredAt", transaction.get("timestamp", "")),
                })

        # Also support exports where timber records are stored in a top-level
        # "timber" dictionary instead of (or in addition to) block transactions.
        if not rows and isinstance(payload, dict) and isinstance(payload.get("timber"), dict):
            for grume_id, record in payload["timber"].items():
                record = record or {}
                rows.append({
                    "Grume ID": record.get("grumeId", grume_id),
                    "Essence": record.get("species", "Unknown") or "Unknown",
                    "Origine": record.get("origin", "Unspecified") or "Unspecified",
                    "Volume (m³)": record.get("volumeM3"),
                    "Diamètre (cm)": record.get("diameterCm"),
                    "Longueur (m)": record.get("lengthM"),
                    "Date de récolte": record.get("harvestDate", ""),
                    "Date d'enregistrement": record.get("registeredAt", ""),
                })

        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame, "The data/forest-forest-blockchain.json file contains no timber registration records."

        for column in ["Volume (m³)", "Diamètre (cm)", "Longueur (m)"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        frame["Date de récolte"] = pd.to_datetime(
            frame["Date de récolte"], format="%d-%m-%Y", errors="coerce"
        )
        frame["Date d'enregistrement"] = pd.to_datetime(
            frame["Date d'enregistrement"], errors="coerce", utc=True
        ).dt.tz_convert(None)

        return frame, None
    except Exception as exc:
        return pd.DataFrame(), f"Could not read data/forest-blockchain.json: {exc}"

stats_data, stats_load_error = load_statistics_records()

# Dropdown options are populated from the values present in blockchain.json.
stats_essence_filter = pn.widgets.Select(
    name="Essence",
    options=["Toutes les essences"] + (
        sorted(stats_data["Essence"].dropna().unique().tolist()) if not stats_data.empty else []
    ),
    value="Toutes les essences",
    sizing_mode="stretch_width"
)
stats_origin_filter = pn.widgets.Select(
    name="Origine",
    options=["Toutes les origines"] + (
        sorted(stats_data["Origine"].dropna().unique().tolist()) if not stats_data.empty else []
    ),
    value="Toutes les origines",
    sizing_mode="stretch_width"
)
stats_refresh_btn = pn.widgets.Button(
    name="Reload JSON data",
    button_type="primary",
    icon="refresh"
)
stats_message = pn.pane.Alert(
    stats_load_error or f"Loaded {len(stats_data):,} timber registration records from data/forest-blockchain.json.",
    alert_type="warning" if stats_load_error else "success"
)
stats_kpis = pn.Row(sizing_mode="stretch_width")
stats_charts = pn.GridBox(ncols=2, sizing_mode="stretch_width", margin=10)

def _filtered_statistics_data():
    if stats_data.empty:
        return stats_data.copy()
    filtered = stats_data.copy()
    if stats_essence_filter.value != "Toutes les essences":
        filtered = filtered[filtered["Essence"] == stats_essence_filter.value]
    if stats_origin_filter.value != "Toutes les origines":
        filtered = filtered[filtered["Origine"] == stats_origin_filter.value]
    return filtered

def _statistics_card(title, plot):
    return pn.Card(
        plot,
        title=title,
        collapsed=False,
        sizing_mode="stretch_width",
        styles={"background": "#ffffff", "border": "1px solid #e5e7eb"}
    )

def render_statistics_dashboard(event=None):
    global stats_data, stats_load_error

    if event is not None and getattr(event, "obj", None) is stats_refresh_btn:
        stats_data, stats_load_error = load_statistics_records()
        stats_essence_filter.options = ["Toutes les essences"] + (
            sorted(stats_data["Essence"].dropna().unique().tolist()) if not stats_data.empty else []
        )
        stats_origin_filter.options = ["Toutes les origines"] + (
            sorted(stats_data["Origine"].dropna().unique().tolist()) if not stats_data.empty else []
        )
        stats_essence_filter.value = "Toutes les essences"
        stats_origin_filter.value = "Toutes les origines"

    if stats_load_error:
        stats_message.object = stats_load_error
        stats_message.alert_type = "danger"
        stats_kpis.objects = []
        stats_charts.objects = [pn.pane.Markdown("### Statistics are unavailable until the JSON file can be read.")]
        return

    frame = _filtered_statistics_data()
    stats_message.object = (
        f"Showing **{len(frame):,}** of **{len(stats_data):,}** registered timber records. "
        "Use the Essence and Origine filters to update all charts."
    )
    stats_message.alert_type = "success"

    total_volume = frame["Volume (m³)"].fillna(0).sum() if not frame.empty else 0
    stats_kpis.objects = [
        metric("Total Grumes", f"{len(frame):,}", "Filtered registrations"),
        metric("Total volume", f"{total_volume:,.2f} m³", "Sum of registered volume"),
        metric("Essences", frame["Essence"].nunique() if not frame.empty else 0, "Distinct species"),
        metric("Origins", frame["Origine"].nunique() if not frame.empty else 0, "Distinct forest origins"),
    ]

    if frame.empty:
        stats_charts.objects = [pn.pane.Markdown("### No records match the selected filters.")]
        return

    # Aggregate registrations by Essence for the bar chart.
    essence_counts = (
        frame.groupby("Essence").size()
        .reset_index(name="Nombre de grumes")
        .sort_values("Nombre de grumes", ascending=False)
    )

    # 1. Bar: number of grumes by Essence.
    bar_plot = essence_counts.hvplot.bar(
        x="Essence", y="Nombre de grumes", title="Bar – Number of Grumes by Essence",
        height=330, rot=35, color="#16866f", tools=["hover", "pan", "wheel_zoom", "reset"],
        responsive=True
    )

    # 2. Barh: total timber volume by Origine.
    origin_volume = (
        frame.groupby("Origine")["Volume (m³)"].sum()
        .sort_values(ascending=True).reset_index()
    )
    barh_plot = origin_volume.hvplot.barh(
        x="Volume (m³)", y="Origine", title="Barh – Total Volume by Origine",
        height=330, color="#d97706", tools=["hover", "pan", "wheel_zoom", "reset"],
        responsive=True
    )

    # 3. Scatter: diameter against volume, with Essence as the color group.
    scatter_frame = frame.dropna(subset=["Diamètre (cm)", "Volume (m³)"])
    scatter_plot = scatter_frame.hvplot.scatter(
        x="Diamètre (cm)", y="Volume (m³)", by="Essence",
        title="Scatter – Diameter vs Volume",
        height=330, size=7, alpha=0.65, legend="right",
        hover_cols=["Grume ID", "Origine", "Longueur (m)"],
        tools=["hover", "pan", "wheel_zoom", "box_zoom", "reset", "save"],
        responsive=True
    )

    # 4. Heatmap: registration counts by Origine and Essence.
    heatmap_data = (
        frame.groupby(["Origine", "Essence"]).size()
        .reset_index(name="Nombre de grumes")
    )
    heatmap_plot = heatmap_data.hvplot.heatmap(
        x="Essence", y="Origine", C="Nombre de grumes",
        title="Heatmap – Grumes by Origine and Essence",
        height=360, cmap="Viridis", colorbar=True,
        tools=["hover", "pan", "wheel_zoom", "reset"], responsive=True
    )

    # 5. Histogram: distribution of timber volumes.
    hist_values = frame.dropna(subset=["Volume (m³)"])
    hist_plot = hist_values.hvplot.hist(
        y="Volume (m³)", bins=25, title="Histogram – Timber Volume Distribution",
        height=330, color="#0f766e", alpha=0.8,
        tools=["hover", "pan", "wheel_zoom", "reset"], responsive=True
    )

    # 6. Line: number of timber harvests over time.
    line_data = (
        frame.dropna(subset=["Date de récolte"])
        .groupby("Date de récolte").size()
        .reset_index(name="Nombre de grumes")
        .sort_values("Date de récolte")
    )
    line_plot = line_data.hvplot.line(
        x="Date de récolte", y="Nombre de grumes",
        title="Line – Timber Harvests Over Time",
        height=330, color="#2563eb", line_width=2, marker="circle",
        tools=["hover", "pan", "wheel_zoom", "box_zoom", "reset", "save"],
        responsive=True
    )

    stats_charts.objects = [
        _statistics_card("1. Bar chart", bar_plot),
        _statistics_card("2. Horizontal bar chart", barh_plot),
        _statistics_card("3. Scatter plot", scatter_plot),
        _statistics_card("4. Heatmap", heatmap_plot),
        _statistics_card("5. Histogram", hist_plot),
        _statistics_card("6. Line chart", line_plot),
    ]

stats_essence_filter.param.watch(render_statistics_dashboard, "value")
stats_origin_filter.param.watch(render_statistics_dashboard, "value")
stats_refresh_btn.on_click(render_statistics_dashboard)

statistics_view = pn.Column(
    "## Statistics graph",
    "Interactive timber registration analytics based on the blockchain JSON export.",
    pn.Row(stats_essence_filter, stats_origin_filter, stats_refresh_btn, sizing_mode="stretch_width"),
    stats_message,
    stats_kpis,
    stats_charts,
    sizing_mode="stretch_width"
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
                           pn.Row(harvest_date, origin),
                           pn.pane.Markdown("### GPS position for the geolocation map"),
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

tabs = pn.Tabs(("Dashboard", dashboard), ("Register timber", register_view), ("Geolocalisation", geo_view),
               ("Record event", event_view), ("Traceability", history_view),
               ("Blockchain explorer", ledger_view), ("Arena integration", arena_view),
               ("Statistics graph", statistics_view),
               dynamic=True, sizing_mode="stretch_both")

statistics_menu_btn = pn.widgets.Button(
    name="Statistics graph", button_type="primary", icon="chart-no-axes-combined",
    sizing_mode="stretch_width"
)
def open_statistics_graph(event):
    render_statistics_dashboard()
    tabs.active = tabs.names.index("Statistics graph")
statistics_menu_btn.on_click(open_statistics_graph)
template = pn.template.FastListTemplate(
    title="Forest Traceability",
    sidebar=[pn.pane.Markdown("## Navigation"), pn.pane.Markdown(
        "Use the tabs to register timber, record events, inspect provenance and verify ledger integrity."),
        statistics_menu_btn,
        pn.pane.Markdown("---"), pn.pane.Markdown("**Technology**\n\nPython Panel\n\nNode.js API\n\nSHA-256 blockchain")],
    main=[header, tabs],
    accent_base_color="#16866f", header_background="#102b26",
    theme="default"
)
refresh_dashboard()
refresh_geo_from_system()
render_statistics_dashboard()
template.servable()
