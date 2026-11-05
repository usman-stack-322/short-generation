import { useState } from 'react';
import { api } from '../services/api';
import { Button, Modal, Notice } from './UI';
import LanguageSelect from './LanguageSelect';
import VoiceStyleSelect from './VoiceStyleSelect';

export default function PersonalityPicker({ rows, value, channelId, language, onChange, onCreated }) {
  const [query,setQuery]=useState(''),[open,setOpen]=useState(false),[adding,setAdding]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [draft,setDraft]=useState({name:'',category:'',research_keywords:'',description:'',preferred_language:language||'en-US',default_voice_style:'auto'});
  const selected=rows.find(row=>row.id===value);
  const searchText=text=>text.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,' ').trim();
  const options=rows.filter(row=>searchText(row.name+' '+row.category).includes(searchText(query)));
  async function save(event){
    event.preventDefault();event.stopPropagation();setBusy(true);setError('');
    try{
      const created=await api('/personalities',{method:'POST',body:JSON.stringify({...draft,category:draft.category||'General',
        research_keywords:draft.research_keywords.split(',').map(v=>v.trim()).filter(Boolean),channel_id:channelId||null})});
      const refreshed=await api('/personalities');onCreated(refreshed,created.id);setAdding(false);setOpen(false);setQuery('');
      setDraft({...draft,name:'',research_keywords:'',description:''});
    }catch(err){setError(err.message);}finally{setBusy(false);}
  }
  return <div className="personality-picker">
    <label htmlFor="personality-search">Personality</label>
    <input id="personality-search" role="combobox" aria-expanded={open} aria-controls="personality-options" aria-autocomplete="list"
      placeholder={selected?.name||'Search or choose personality'} value={query} onFocus={()=>setOpen(true)}
      onChange={e=>{setQuery(e.target.value);setOpen(true);}} onKeyDown={e=>{
        if(e.key==='Escape')setOpen(false);
        if(e.key==='Enter'&&open){e.preventDefault();if(options[0]){onChange(options[0].id);setOpen(false);setQuery('');}}
        if(e.key==='ArrowDown'){e.preventDefault();document.querySelector('#personality-options [role="option"]')?.focus();}
      }}/>
    {open&&<div id="personality-options" className="personality-options" role="listbox" aria-label="Personalities">
      {options.map(row=><button type="button" role="option" aria-selected={row.id===value} key={row.id} onClick={()=>{onChange(row.id);setOpen(false);setQuery('');}}>{row.name}<small>{row.category}</small></button>)}
      {!options.length&&<p>No matching personalities.</p>}
      <button type="button" onClick={()=>{setAdding(true);setDraft({...draft,preferred_language:language||'en-US'});}}>+ Add new personality</button>
    </div>}
    {!open&&<Button type="button" variant="secondary" onClick={()=>setAdding(true)}>+ Add new personality</Button>}
    {adding&&<Modal title="Add new personality" onClose={()=>setAdding(false)}><form className="form-stack" onSubmit={save}>
      <label>Name<input autoFocus required minLength={2} value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
      <label>Category<input value={draft.category} onChange={e=>setDraft({...draft,category:e.target.value})}/></label>
      <label>Research keywords<input placeholder="Separate keywords with commas" value={draft.research_keywords} onChange={e=>setDraft({...draft,research_keywords:e.target.value})}/></label>
      <label>Description<textarea value={draft.description} onChange={e=>setDraft({...draft,description:e.target.value})}/></label>
      <LanguageSelect label="Default language" value={draft.preferred_language} onChange={value=>setDraft({...draft,preferred_language:value})}/>
      <VoiceStyleSelect value={draft.default_voice_style} onChange={value=>setDraft({...draft,default_voice_style:value})}/>
      <small>{localStorage.getItem('role')==='OWNER'?'Shared with the selected channel.':'Private to you until the owner shares it.'}</small>
      <Notice>{error}</Notice><Button type="submit" loading={busy}>Save personality</Button>
    </form></Modal>}
  </div>;
}
