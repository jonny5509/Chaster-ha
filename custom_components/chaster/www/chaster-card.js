/* Chaster Lovelace card
 * Responsive, theme-aware dashboard card with optional entity overrides.
 */
class ChasterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._root = document.createElement("div");
    this.shadowRoot.appendChild(this._root);
    this._config = {};
    this._hass = null;
    this._busy = new Set();
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Chaster Card: configuration must be an object");
    }
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._config.show_actions === false ? 5 : 8;
  }

  static getStubConfig() {
    return { type: "custom:chaster-card" };
  }

  _states() {
    return this._hass?.states ? Object.values(this._hass.states) : [];
  }

  _find(key, ...suffixes) {
    const configured = this._config?.entities?.[key];
    if (configured && this._hass?.states?.[configured]) {
      return this._hass.states[configured];
    }
    const wanted = suffixes.map((value) => String(value).toLowerCase().replaceAll(" ", "_"));
    return this._states().find((entity) => {
      const id = String(entity.entity_id || "").toLowerCase();
      const name = String(entity.attributes?.friendly_name || "").toLowerCase().replaceAll(" ", "_");
      if (!id.includes("chaster") && !name.includes("chaster")) return false;
      return wanted.some((suffix) =>
        id.endsWith("_" + suffix) ||
        name.endsWith(suffix) ||
        name.endsWith("chaster_" + suffix)
      );
    }) || null;
  }

  _findButton(action) {
    const key = action;
    const configured = this._config?.entities?.[key];
    if (configured && this._hass?.states?.[configured]) {
      return this._hass.states[configured];
    }
    const role = this._config.role === "keyholder" ? "keyholder" : "wearer";
    const roleSuffix = "_" + role + "_" + action;
    const wantedName = action.replaceAll("_", " ");
    return this._states().find((entity) => {
      const id = String(entity.entity_id || "").toLowerCase();
      if (!id.startsWith("button.") || (!id.includes("chaster"))) return false;
      const name = String(entity.attributes?.friendly_name || "").toLowerCase();
      return id.endsWith(roleSuffix) ||
        (id.endsWith("_" + action) && name.includes(wantedName) && name.includes(role)) ||
        (name.includes(wantedName) && name.includes(role));
    }) || null;
  }

  _value(entity) {
    if (!entity || ["unknown", "unavailable", "none"].includes(String(entity.state).toLowerCase())) {
      return "—";
    }
    try {
      if (typeof this._hass?.formatEntityState === "function") {
        return this._hass.formatEntityState(entity);
      }
    } catch (_error) {
      // Fall back to the raw state on older Home Assistant versions.
    }
    return entity.state;
  }

  _escape(value) {
    return String(value ?? "—")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async _press(entityId, index) {
    if (!this._hass || !entityId || this._busy.has(index)) return;
    this._busy.add(index);
    this._render();
    try {
      await this._hass.callService("button", "press", { entity_id: entityId });
    } catch (error) {
      console.error("Chaster Card: unable to run button action", error);
    } finally {
      this._busy.delete(index);
      this._render();
    }
  }

  _render() {
    if (!this._hass || !this._root) return;

    const role = this._config.role === "keyholder" ? "keyholder" : "wearer";
    const values = [
      ["◉", "Lock title", this._find("lock_title", role === "keyholder" ? "keyholder_lock_title" : "wearer_lock_title", role === "keyholder" ? "keyholder_lock_title" : "my_lock_lock_title")],
      ["⏱", "Time locked", this._find("time_locked", role === "keyholder" ? "keyholder_time_locked" : "my_lock_time_locked", "time_locked")],
      ["⌛", "Time remaining", this._find("time_remaining", role === "keyholder" ? "keyholder_time_remaining" : "my_lock_time_remaining", "time_remaining")],
      ["⭐", "Task points", this._find("task_points", role === "keyholder" ? "keyholder_task_points" : "my_lock_task_points", "task_points")],
      ["🎯", "Points required", this._find("task_points_required", role === "keyholder" ? "keyholder_task_points_required" : "my_lock_task_points_required", "task_points_required")],
      ["↘", "Points remaining", this._find("task_points_remaining", role === "keyholder" ? "keyholder_task_points_remaining" : "my_lock_task_points_remaining", "task_points_remaining")],
      ["👤", role === "keyholder" ? "Wearer" : "Keyholder", this._find(role === "keyholder" ? "wearer_username" : "keyholder_username", role === "keyholder" ? "keyholder_device_wearer_username" : "my_lock_keyholder_username", role === "keyholder" ? "wearer_username" : "keyholder_username")],
      ["🔒", "Lock type", this._find("lock_type", role === "keyholder" ? "keyholder_lock_type" : "wearer_lock_type", "lock_type")],
    ];

    const binary = [
      ["Locked", this._find("locked", role + "_locked")],
      ["Ready to unlock", this._find("ready_to_unlock", role + "_ready_to_unlock")],
      ["Frozen", this._find("frozen", role + "_frozen")],
      ["Task assigned", this._find("task_assigned", role + "_task_assigned")],
    ];

    const actionDefs = [
      ["Refresh", "refresh"],
      ["Refresh history", "history"],
      ["+1 day", "add_1_day"],
      ["+1 hour", "add_1_hour"],
      ["−1 day", "subtract_1_day"],
      ["−1 hour", "subtract_1_hour"],
      ["Freeze", "freeze"],
      ["Unfreeze", "unfreeze"],
      ["Unlock", "unlock"],
      ["Emergency unlock", "emergency_unlock"],
      ["Archive", "archive"],
    ];
    const actions = actionDefs.map(([label, key]) => ({
      label,
      key,
      entity: this._findButton(key),
    }));

    const visibleValues = values.filter(([, entity]) => entity);
    const visibleBinary = binary.filter(([, entity]) => entity);
    const showActions = this._config.show_actions !== false;
    const title = this._escape(this._config.title || "Chaster");

    this._root.innerHTML = `
      <style>
        :host { display: block; min-width: 0; }
        ha-card {
          overflow: hidden;
          color: var(--primary-text-color);
          background: var(--ha-card-background, var(--card-background-color, var(--paper-card-background-color)));
          border: 1px solid var(--divider-color);
          border-radius: var(--ha-card-border-radius, 16px);
          box-shadow: var(--ha-card-box-shadow, none);
        }
        .card { padding: 16px; font-family: var(--paper-font-body1_-_font-family, inherit); }
        .heading { margin: 0 0 12px; color: var(--primary-text-color); font-size: 1.15rem; font-weight: 600; }
        .rows { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 8px; }
        .row {
          display: flex; align-items: center; min-height: 62px; min-width: 0;
          box-sizing: border-box; padding: 10px 12px; border-radius: 12px;
          background: var(--secondary-background-color);
          border: 1px solid var(--divider-color);
        }
        .row-icon { width: 34px; flex: 0 0 34px; color: var(--secondary-text-color); font-size: 20px; text-align: center; }
        .row-content { min-width: 0; flex: 1; padding-left: 8px; }
        .label { color: var(--secondary-text-color); font-size: 11px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; }
        .value { margin-top: 4px; color: var(--primary-text-color); font-size: 16px; font-weight: 600; overflow-wrap: anywhere; }
        .statuses { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
        .status { padding: 6px 10px; border: 1px solid var(--divider-color); border-radius: 999px; color: var(--secondary-text-color); font-size: 12px; font-weight: 600; }
        .status.on { color: var(--success-color, var(--primary-color)); border-color: var(--success-color, var(--primary-color)); }
        .actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
        .action {
          min-width: 0; min-height: 44px; padding: 8px 12px; border: 0; border-radius: 12px;
          background: var(--primary-color); color: var(--text-primary-color, white);
          font: inherit; font-weight: 600; cursor: pointer;
        }
        .action:hover:not(:disabled) { filter: brightness(1.08); }
        .action:focus-visible { outline: 2px solid var(--primary-text-color); outline-offset: 2px; }
        .action:disabled { opacity: .45; cursor: not-allowed; }
        .empty { color: var(--secondary-text-color); padding: 8px 0; }
        @media (max-width: 360px) { .card { padding: 12px; } .value { font-size: 14px; } }
      </style>
      <ha-card>
        <div class="card">
          <h2 class="heading">${title}</h2>
          <div class="rows">
            ${visibleValues.length ? visibleValues.map(([label, entity, icon]) =>
              this._row(icon, label, this._value(entity))
            ).join("") : '<div class="empty">No Chaster entities found. Check that the integration is loaded, or set entity IDs in the card configuration.</div>'}
          </div>
          ${visibleBinary.length ? `<div class="statuses">${visibleBinary.map(([label, entity]) =>
            `<span class="status ${entity.state === "on" ? "on" : ""}">${this._escape(label)}: ${entity.state === "on" ? "Yes" : entity.state === "off" ? "No" : this._escape(this._value(entity))}</span>`
          ).join("")}</div>` : ""}
          ${showActions ? `
            <div class="actions">
              ${actions.map((action, index) => `
                <button class="action" data-action="${index}" ${!action.entity || ["unavailable", "unknown"].includes(action.entity.state) || this._busy.has(index) ? "disabled" : ""}>
                  ${this._busy.has(index) ? "Working…" : this._escape(action.label)}
                </button>
              `).join("")}
            </div>
          ` : ""}
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".action").forEach((element) => {
      element.addEventListener("click", () => {
        const action = actions[Number(element.dataset.action)];
        if (action?.entity) this._press(action.entity.entity_id, Number(element.dataset.action));
      });
    });
  }

  _row(icon, label, value) {
    return `<div class="row"><div class="row-icon" aria-hidden="true">${this._escape(icon)}</div><div class="row-content"><div class="label">${this._escape(label)}</div><div class="value">${this._escape(value)}</div></div></div>`;
  }
}

if (!customElements.get("chaster-card")) {
  customElements.define("chaster-card", ChasterCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "chaster-card")) {
  window.customCards.push({
    type: "chaster-card",
    name: "Chaster Card",
    description: "Chaster session status and controls.",
    preview: true,
    documentationURL: "https://github.com/jonny5509/Chaster-ha",
    getEntitySuggestion: (hass, entityId) => {
      if (!entityId.toLowerCase().includes("chaster")) return null;
      return { config: { type: "custom:chaster-card" } };
    },
  });
}
