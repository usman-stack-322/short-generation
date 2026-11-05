import { useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import { api } from '../services/api';

export default function Notifications() {
  const [rows,setRows] = useState([]);
  const [open,setOpen] = useState(false);
  const [error,setError] = useState('');
  useEffect(() => {
    let live=true;
    async function load() { try { const data=await api('/notifications'); if(live) {setRows(data);setError('');} } catch(err) {if(live)setError(err.message);} }
    load(); const timer=setInterval(load,10000);
    return () => {live=false;clearInterval(timer);};
  },[]);
  async function mark(row) {
    try { await api(`/notifications/${row.id}/read`,{method:'POST'});setRows(old=>old.map(item=>item.id===row.id?{...item,read:true}:item)); }
    catch(err) {setError(err.message);}
  }
  return <div className="notification-wrap"><button className="icon-button notification" aria-label="Notifications" aria-expanded={open} onClick={()=>setOpen(!open)}><Bell size={17}/>{rows.some(row=>!row.read)&&<i/>}</button>{open&&<section className="notification-list panel"><strong>Notifications</strong>{error&&<p role="alert">{error}</p>}{!rows.length&&<p>No notifications yet.</p>}{rows.map(row=><button key={row.id} className={row.read?'read':''} onClick={()=>mark(row)}><strong>{row.title}</strong><span>{row.message}</span><small>{new Date(row.created_at).toLocaleString()}</small></button>)}</section>}</div>;
}
