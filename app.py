import os
import json
from datetime import datetime

import pandas as pd
import panel as pn
import requests

# Optional charting dependency. The app still works if hvplot is unavailable.
try:
    import hvplot.pandas  # noqa: F401
    HVPLOT_AVAILABLE = True
except Exception:
    HVPLOT_AVAILABLE = False

pn.extension("tabulator", sizing_mode="stretch_width")

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
API_URL = os.getenv(
    "BLOCKCHAIN_API_URL",
    "http://127.0.0.1:3000/api/v1"
).rstrip("/")
API_KEY = os.getenv("API_KEY", "dev-change-this-key")
HEADERS = {"x-api-key": API_KEY}


# ---------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------
def api_get(path):
    """Call a GET endpoint on the Node.js blockchain API."""
    try:
        response = requests.get(
            API_URL + path,
            headers=HEADERS,
            timeout=8
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        return {"error": str(exc)}
    except ValueError:
        return {"error": "The API returned an invalid JSON response."}


def api_post(path, payload):
    """Call a POST endpoint on the Node.js blockchain API."""
    try:
        response = requests.post(
            API_URL + path,
            json=payload,
            headers=HEADERS,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as exc:
        try:
            return {"error": exc.response.json().get("error", str(exc))}
        except Exception:
            return {"error": str(exc)}
    except requests.exceptions.RequestException as exc:
        return {"error": str(exc)}
    except ValueError:
        return {"error": "The API returned an invalid JSON response."}


def message_panel(text="", kind="info"):
    """Create a compatible message using Markdown rather than pn.pane.Alert."""
    colors = {
        "success": ("#e8f5e9", "#1b5e20"),
        "danger": ("#ffebee", "#b71c1c"),
        "warning": ("#fff8e1", "#8d6e00"),
        "info": ("#e3f2fd", "#0d47a1"),
        "light": ("#f3f4f6", "#374151"),
    }
    background, foreground = colors.get(kind, colors["info"])
    return pn.pane.Markdown(
        text,
        styles={
            "background": background,
            "color": foreground,
            "padding": "10px 14px",
            "border-radius": "8px",
            "border": "1px solid " + foreground,
        },
        sizing_mode="stretch_width",
    )


def show_message(target, text, kind="info"):
    """Update a Markdown message pane."""
    colors = {
        "success": ("#e8f5e9", "#1b5e20"),
        "danger": ("#ffebee", "#b71c1c"),
        "warning": ("#fff8e1", "#8d6e00"),
        "info": ("#e3f2fd", "#0d47a1"),
        "light": ("#f3f4f6", "#374151"),
    }
    background, foreground = colors.get(kind, colors["info"])
    target.object = text
    target.styles = {
        "background": background,
        "color": foreground,
        "padding": "10px 14px",
        "border-radius": "8px",
        "border": "1px solid " + foreground,
    }


def metric(title, value, note=""):
    return pn.Card(
        pn.Column(
            pn.pane.Markdown(
                f"<div style='font-size:30px;font-weight:700;color:#16866f'>{value}</div>"
                f"<div style='font-size:15px;font-weight:600'>{title}</div>"
                f"<div style='font-size:11px;color:#64748b'>{note}</div>"
            ),
            sizing_mode="stretch_width",
        ),
        styles={
            "background": "#ffffff",
            "border": "1px solid #e5e7eb",
            "border-radius": "12px",
        },
        sizing_mode="stretch_width",
    )


# ---------------------------------------------------------------------
# Shared dashboard components
# ---------------------------------------------------------------------
status = message_panel("Connecting to blockchain API...", "info")
kpi_row = pn.Row(sizing_mode="stretch_width")
chain_table = pn.widgets.Tabulator(
    pd.DataFrame(),
    pagination="local",
    page_size=10,
    height=330,
    sizing_mode="stretch_width",
)
timber_table = pn.widgets.Tabulator(
    pd.DataFrame(),
    pagination="local",
    page_size=10,
    height=330,
    sizing_mode="stretch_width",
)
history_table = pn.widgets.Tabulator(
    pd.DataFrame(),
    pagination="local",
    page_size=10,
    height=300,
    sizing_mode="stretch_width",
)
chart_area = pn.Column(sizing_mode="stretch_width")


def refresh_dashboard():
    health = api_get("/health")

    if "error" in health:
        show_message(status, "Blockchain API unavailable: " + health["error"], "danger")
        kpi_row.objects = [
            metric("Total blocks", "—", "API unavailable"),
            metric("Registered timber", "—", "API unavailable"),
            metric("Pending transactions", "—", "API unavailable"),
            metric("Connection", "Offline", "Check Node.js backend"),
        ]
        return

    show_message(
        status,
        "Connected to " + str(health.get("service", "Forest Traceability Blockchain API")),
        "success",
    )

    chain_result = api_get("/chain")
    timber_result = api_get("/timber")

    if "error" in chain_result:
        show_message(status, "API connected, but ledger could not be loaded: " + chain_result["error"], "danger")
        return

    blocks = chain_result.get("chain", [])
    timber_items = timber_result.get("timber", []) if "error" not in timber_result else []
    pending_count = chain_result.get("pendingTransactions", 0)

    kpi_row.objects = [
        metric("Total blocks", len(blocks), "Blocks in local ledger"),
        metric("Registered timber", len(timber_items), "Unique grume IDs"),
        metric("Pending transactions", pending_count, "Waiting to be committed"),
        metric("Blockchain status", "Operational", "Node.js API connected"),
    ]

    chain_rows = []
    for block in blocks:
        chain_rows.append({
            "Index": block.get("index"),
            "Timestamp": block.get("timestamp"),
            "Transactions": len(block.get("transactions", [])),
            "Previous hash": str(block.get("previousHash", ""))[:20] + "...",
            "Block hash": str(block.get("hash", ""))[:20] + "...",
            "Nonce": block.get("nonce"),
        })
    chain_table.value = pd.DataFrame(chain_rows)

    timber_table.value = pd.DataFrame(timber_items)

    if blocks and HVPLOT_AVAILABLE:
        chart_data = pd.DataFrame([
            {
                "Block": block.get("index"),
                "Transactions": len(block.get("transactions", [])),
            }
            for block in blocks
        ])
        if not chart_data.empty:
            chart_area.objects = [
                chart_data.hvplot.bar(
                    x="Block",
                    y="Transactions",
                    height=280,
                    title="Transactions per block",
                    color="#16866f",
                    ylabel="Transactions",
                    xlabel="Block",
                    rot=0,
                )
            ]
        else:
            chart_area.objects = [pn.pane.Markdown("No blockchain data available yet.")]
    elif blocks:
        chart_area.objects = [
            pn.pane.Markdown(
                "Install `hvplot` to display the transactions chart. "
                "The tables and blockchain functions remain available."
            )
        ]
    else:
        chart_area.objects = [
            pn.pane.Markdown("No blocks are available yet.")
        ]


refresh_btn = pn.widgets.Button(
    name="Refresh dashboard",
    button_type="primary",
    width=180,
)


def on_refresh(event):
    refresh_dashboard()


refresh_btn.on_click(on_refresh)


# ---------------------------------------------------------------------
# Timber registration
# ---------------------------------------------------------------------
grume_id = pn.widgets.TextInput(
    name="Unique timber / grume ID",
    placeholder="e.g. RCA-LOB-2026-0001",
)
species = pn.widgets.TextInput(
    name="Species",
    placeholder="e.g. Sapelli",
)
volume = pn.widgets.FloatInput(
    name="Volume (m³)",
    value=1.0,
    start=0.001,
)
harvest_date = pn.widgets.DatePicker(
    name="Harvest date",
    value=datetime.now().date(),
)
origin = pn.widgets.TextInput(
    name="Forest concession / origin",
)
gps = pn.widgets.TextInput(
    name="GPS coordinates",
    placeholder="Latitude, longitude",
)
register_msg = pn.pane.Markdown("", visible=False)


def register_timber(event):
    if not grume_id.value.strip() or not species.value.strip():
        register_msg.visible = True
        show_message(register_msg, "Please provide both a grume ID and species.", "warning")
        return

    result = api_post(
        "/timber",
        {
            "grumeId": grume_id.value.strip(),
            "species": species.value.strip(),
            "volumeM3": volume.value,
            "harvestDate": str(harvest_date.value) if harvest_date.value else None,
            "origin": origin.value.strip(),
            "gps": gps.value.strip(),
        },
    )

    register_msg.visible = True
    if "error" in result:
        show_message(register_msg, result["error"], "danger")
    else:
        show_message(
            register_msg,
            "Timber registered and committed to the blockchain.\n\n"
            "```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```",
            "success",
        )
        refresh_dashboard()


register_btn = pn.widgets.Button(
    name="Register timber",
    button_type="success",
    width=180,
)
register_btn.on_click(register_timber)


# ---------------------------------------------------------------------
# Traceability event registration
# ---------------------------------------------------------------------
event_grume = pn.widgets.TextInput(name="Grume ID")
event_type = pn.widgets.Select(
    name="Traceability event",
    options=[
        "HARVEST",
        "FOREST_GATE",
        "TRANSPORT",
        "SAWMILL_INTAKE",
        "PROCESSING",
        "WAREHOUSE",
        "SALE",
        "EXPORT",
    ],
)
actor = pn.widgets.TextInput(name="Responsible operator / organization")
location = pn.widgets.TextInput(name="Location")
event_notes = pn.widgets.TextAreaInput(name="Notes", height=100)
event_msg = pn.pane.Markdown("", visible=False)


def add_event(event):
    if not event_grume.value.strip():
        event_msg.visible = True
        show_message(event_msg, "Please enter a grume ID.", "warning")
        return

    result = api_post(
        "/events",
        {
            "grumeId": event_grume.value.strip(),
            "eventType": event_type.value,
            "actor": actor.value.strip(),
            "location": location.value.strip(),
            "notes": event_notes.value.strip(),
        },
    )

    event_msg.visible = True
    if "error" in result:
        show_message(event_msg, result["error"], "danger")
    else:
        show_message(
            event_msg,
            "Traceability event committed to the blockchain.\n\n"
            "```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```",
            "success",
        )
        refresh_dashboard()


event_btn = pn.widgets.Button(
    name="Add blockchain transaction",
    button_type="primary",
    width=240,
)
event_btn.on_click(add_event)


# ---------------------------------------------------------------------
# Timber history
# ---------------------------------------------------------------------
history_id = pn.widgets.TextInput(
    name="Grume ID",
    placeholder="Enter a registered timber ID",
)
history_msg = pn.pane.Markdown("", visible=False)


def load_history(event):
    if not history_id.value.strip():
        history_msg.visible = True
        show_message(history_msg, "Enter a grume ID to search.", "warning")
        return

    from urllib.parse import quote

    result = api_get(
        "/timber/" + quote(history_id.value.strip(), safe="") + "/history"
    )

    history_msg.visible = True
    if "error" in result:
        show_message(history_msg, result["error"], "danger")
        history_table.value = pd.DataFrame()
    else:
        show_message(history_msg, "Traceability history loaded successfully.", "success")
        history_table.value = pd.DataFrame(result.get("history", []))


history_btn = pn.widgets.Button(
    name="Load traceability history",
    button_type="primary",
    width=220,
)
history_btn.on_click(load_history)


# ---------------------------------------------------------------------
# Blockchain verification and explorer
# ---------------------------------------------------------------------
verify_result = pn.pane.Markdown(
    "Run ledger verification to inspect blockchain integrity."
)
explorer = pn.Column(sizing_mode="stretch_width")


def verify_ledger(event):
    result = api_get("/ledger/verify")
    if "error" in result:
        show_message(verify_result, result["error"], "danger")
        return

    if result.get("valid", False):
        show_message(
            verify_result,
            "Blockchain verification successful.\n\n"
            f"- Blocks checked: **{result.get('blocksChecked', 0)}**\n"
            f"- Checked at: **{result.get('checkedAt', 'N/A')}**",
            "success",
        )
    else:
        show_message(
            verify_result,
            "Blockchain verification failed.\n\n"
            "```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```",
            "danger",
        )


verify_btn = pn.widgets.Button(
    name="Verify entire blockchain",
    button_type="warning",
    width=230,
)
verify_btn.on_click(verify_ledger)


def load_explorer(event):
    result = api_get("/chain")
    if "error" in result:
        explorer.objects = [message_panel(result["error"], "danger")]
        return

    blocks = result.get("chain", [])
    if not blocks:
        explorer.objects = [pn.pane.Markdown("No blocks found.")]
        return

    block_panels = []
    for block in blocks:
        block_panels.append(
            pn.Card(
                pn.pane.JSON(block, depth=4),
                title=f"Block {block.get('index')} — {len(block.get('transactions', []))} transaction(s)",
                collapsed=True,
                sizing_mode="stretch_width",
            )
        )
    explorer.objects = block_panels


explorer_btn = pn.widgets.Button(
    name="Load blockchain blocks",
    button_type="primary",
    width=200,
)
explorer_btn.on_click(load_explorer)


# ---------------------------------------------------------------------
# Arena integration information
# ---------------------------------------------------------------------
arena_url = pn.widgets.TextInput(
    name="Arena API base URL",
    placeholder="https://your-arena-server.example/api",
)
arena_token = pn.widgets.PasswordInput(name="Arena access token")
arena_note = pn.pane.Markdown(
    """
### Integration status

The blockchain backend exposes REST endpoints that can be connected to OpenForis Arena.

**Important:** the current project provides the integration boundary and configuration fields,
but does not yet synchronize records with Arena. A dedicated adapter must be configured
with your Arena server URL, API authentication method, data model and permissions.
"""
)


# ---------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------
header = pn.Column(
    pn.Row(
        pn.pane.Markdown(
            "# 🌳 Forest Traceability Blockchain",
            styles={"color": "#ffffff", "margin": "0"},
        ),
        pn.Spacer(),
        refresh_btn,
        sizing_mode="stretch_width",
    ),
    pn.pane.Markdown(
        "**Timber legality · Chain of custody · Verifiable digital records**",
        styles={"color": "#d1d5db"},
    ),
    styles={
        "background": "#102b26",
        "padding": "18px",
        "border-radius": "12px",
    },
)

dashboard = pn.Column(
    status,
    kpi_row,
    pn.pane.Markdown("## Blockchain activity"),
    chart_area,
    pn.pane.Markdown("## Latest blockchain blocks"),
    chain_table,
    pn.pane.Markdown("## Registered timber"),
    timber_table,
)

register_view = pn.Column(
    pn.pane.Markdown("## Register timber"),
    pn.pane.Markdown(
        "Create a unique timber identity before recording chain-of-custody events."
    ),
    grume_id,
    species,
    pn.Row(volume, harvest_date),
    origin,
    gps,
    register_btn,
    register_msg,
)

event_view = pn.Column(
    pn.pane.Markdown("## Record a traceability event"),
    pn.pane.Markdown(
        "Record harvesting, transport, processing, warehousing, sale or export."
    ),
    event_grume,
    event_type,
    actor,
    location,
    event_notes,
    event_btn,
    event_msg,
)

history_view = pn.Column(
    pn.pane.Markdown("## Timber traceability history"),
    history_id,
    history_btn,
    history_msg,
    history_table,
)

ledger_view = pn.Column(
    pn.pane.Markdown("## Blockchain explorer"),
    verify_btn,
    verify_result,
    pn.Spacer(height=18),
    pn.pane.Markdown("### Blockchain blocks"),
    explorer_btn,
    explorer,
)

arena_view = pn.Column(
    pn.pane.Markdown("## OpenForis Arena integration"),
    arena_note,
    arena_url,
    arena_token,
)

tabs = pn.Tabs(
    ("Dashboard", dashboard),
    ("Register timber", register_view),
    ("Record event", event_view),
    ("Traceability", history_view),
    ("Blockchain explorer", ledger_view),
    ("Arena integration", arena_view),
    dynamic=True,
    sizing_mode="stretch_both",
)

template = pn.template.FastListTemplate(
    title="Forest Traceability",
    sidebar=[
        pn.pane.Markdown("## Navigation"),
        pn.pane.Markdown(
            "Use the tabs to register timber, record events, inspect provenance "
            "and verify ledger integrity."
        ),
        pn.pane.Markdown("---"),
        pn.pane.Markdown(
            "**Technology**\n\n"
            "- Python Panel\n"
            "- Node.js API\n"
            "- SHA-256 hash-linked ledger"
        ),
    ],
    main=[header, tabs],
    accent_base_color="#16866f",
    header_background="#102b26",
    theme="default",
)

# Load current API information when the Panel app starts.
refresh_dashboard()
template.servable()
