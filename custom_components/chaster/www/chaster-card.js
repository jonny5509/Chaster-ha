class ChasterCard extends HTMLElement {
  setConfig(config){this._config=config||{};this._render();}
  set hass(hass){this._hass=hass;this._render();}
  getCardSize(){return 6;}
  _find(...names){if(!this._hass?.states)return null;const wanted=names.map(n=>n.toLowerCase().replaceAll(" ","_"));return Object.values(this._hass.states).find(e=>{const id=e.entity_id.toLowerCase(),name=String(e.attributes?.friendly_name||"").toLowerCase().replaceAll(" ","_");if(!id.includes("chaster")&&!name.includes("chaster"))return false;return wanted.some(n=>id.endsWith("_"+n)||name.endsWith(n));})||null;}
  _value(e){return !e||["unknown","unavailable"].includes(e.state)?"—":e.state;}
  _press(e){if(e)this._hass.callService("button","press",{entity_id:e.entity_id});}
  _render(){if(!this._hass)return;const vals=[["⏱","Time locked",this._find("my_lock_time_locked","time_locked")],["⌛","Time remaining",this._find("my_lock_time_remaining","time_remaining")],["⏱","Maximum remaining",this._find("my_lock_max_time_remaining","maximum_time_remaining")],["⭐","Task points",this._find("my_lock_task_points","task_points")]];const btns=["refresh","refresh_history","add_1_day","add_1_hour","subtract_1_day","subtract_1_hour","unlock","emergency_unlock"].map(n=>this._find(n)).filter(e=>e?.entity_id?.startsWith("button."));this.innerHTML='<ha-card><div class="card"><div class="rows">'+vals.map(v=>'<div class="row"><span>'+v[0]+'</span><div><b>'+v[1]+'</b><strong>'+this._value(v[2])+'</strong></div></div>').join("")+'</div><div class="actions">'+btns.map((e,i)=>'<button data-i="'+i+'"'+(e.state==="unavailable"?" disabled":"")+'>'+(e.attributes.friendly_name||"Action")+'</button>').join("")+'</div></div></ha-card><style>:host{display:block}ha-card{overflow:hidden;border-radius:24px;background:#1b1d1e;color:#f4f5f7;border:1px solid #34383b}.card{padding:16px;font-family:var(--paper-font-body1_-_font-family,Arial,sans-serif)}.rows{display:grid;gap:9px}.row{display:flex;align-items:center;min-height:65px;border-radius:17px;background:#242729;padding:10px 14px}.row>span{width:40px;font-size:24px}.row div{display:grid}.row b{color:#aeb7c5;font-size:13px;text-transform:uppercase;letter-spacing:.6px}.row strong{font-size:18px;margin-top:4px}.actions{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;margin-top:12px}button{min-height:48px;border:0;border-radius:15px;background:#242729;color:#f4f5f7;font:inherit;font-weight:700}button:disabled{opacity:.4}</style>';this.querySelectorAll("button").forEach(el=>el.onclick=()=>this._press(btns[Number(el.dataset.i)]));}
}
customElements.define("chaster-card",ChasterCard);
window.customCards=window.customCards||[];
window.customCards.push({
  type:"chaster-card",
  name:"Chaster Card",
  description:"Chaster session status and controls.",
  preview:true,
  getEntitySuggestion: (hass, entityId) => {
    if (!entityId.toLowerCase().includes("chaster")) return null;
    return { config: { type: "custom:chaster-card" } };
  },
});
