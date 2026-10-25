import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { type JsonValue, isObject } from './configuration';

interface JsonFieldsProps {
  value: JsonValue;
  onChange: (value: JsonValue) => void;
  label?: string;
  path?: string;
}

export function JsonFields({ value, onChange, label = 'Value', path = label }: JsonFieldsProps) {
  if (Array.isArray(value)) return (
    <div className="config-array">
      {value.map((item, index) => (
        <div className="config-array-item" key={index}>
          <div className="config-item-heading">
            <span>{isObject(item) ? String(item.name ?? item.label ?? item.key ?? `Item ${index + 1}`) : `Instruction / item ${index + 1}`}</span>
            <div className="config-item-actions">
              <button type="button" className="icon-button" aria-label={`Move ${path} ${index + 1} up`} disabled={index === 0} onClick={() => { const next = [...value]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange(next); }}><ArrowUp size={13} /></button>
              <button type="button" className="icon-button" aria-label={`Move ${path} ${index + 1} down`} disabled={index === value.length - 1} onClick={() => { const next = [...value]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; onChange(next); }}><ArrowDown size={13} /></button>
              <button type="button" className="icon-button" aria-label={`Remove ${path} ${index + 1}`} onClick={() => onChange(value.filter((_, i) => i !== index))}><Trash2 size={13} /></button>
            </div>
          </div>
          <JsonFields value={item} label={isObject(item) ? label : `Item ${index + 1}`} path={`${path}.${index}`} onChange={(next) => onChange(value.map((entry, i) => i === index ? next : entry))} />
        </div>
      ))}
      <button className="button button-outline" type="button" onClick={() => onChange([...value, value.length && isObject(value[0]) ? { ...value[0], key: '' } : ''])}><Plus size={13} />Add item</button>
    </div>
  );
  if (isObject(value)) return (
    <div className="config-fields">
      {Object.entries(value).map(([key, item]) => (
        <JsonFields key={key} value={item} label={key.replace(/_/g, ' ')} path={`${path}.${key}`} onChange={(next) => onChange({ ...value, [key]: next })} />
      ))}
    </div>
  );
  const id = `field-${path}`;
  return (
    <div className={`config-field${typeof value === 'boolean' ? ' config-checkbox' : ''}`}>
      <label htmlFor={id}>{label}</label>
      {typeof value === 'boolean' ? <input id={id} type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} />
        : typeof value === 'number' || value === null ? (
          <div className="config-number">
            <input id={id} type="number" step="any" value={value ?? ''} placeholder="Not configured" onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))} />
            {value !== null && <button type="button" className="text-button" onClick={() => onChange(null)}>Clear</button>}
          </div>
        ) : <textarea id={id} rows={value.length > 130 ? 4 : value.length > 70 ? 2 : 1} value={value} spellCheck={false} onChange={(event) => onChange(event.target.value)} />}
    </div>
  );
}
