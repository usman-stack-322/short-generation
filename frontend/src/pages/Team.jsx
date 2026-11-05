import { useEffect,useState } from 'react';
import { api } from '../services/api';
import { PageHeader } from '../components/Shell';
import { Button,Notice } from '../components/UI';

export default function Team(){
  const [members,setMembers]=useState([]),[audit,setAudit]=useState([]),[me,setMe]=useState(null),[error,setError]=useState(''),[invitation,setInvitation]=useState(null);
  async function load(){try{const [m,a,u]=await Promise.all([api('/members'),api('/members/audit'),api('/auth/me')]);setMembers(m);setAudit(a);setMe(u);}catch(e){setError(e.message);}}
  useEffect(()=>{load();},[]);
  async function change(id,body){try{await api('/members/'+id,{method:'PATCH',body:JSON.stringify(body)});await load();}catch(e){setError(e.message);}}
  return <><PageHeader title="Admin Panel" description="Manage account access. Member channels, media and OAuth credentials remain private."/><Notice>{error}</Notice>
    <section className="panel review-detail"><h2>Members</h2><div className="table-wrap"><table><thead><tr><th>Member</th><th>Role</th><th>Access</th><th>Admin delegation</th></tr></thead><tbody>{members.map(m=><tr key={m.id}><td>{m.name}<br/>{m.email}</td><td><select aria-label={'Role for '+m.name} value={m.role} disabled={!(me?.role==='OWNER'||me?.can_manage_admins)||m.role==='OWNER'&&me?.role!=='OWNER'} onChange={e=>change(m.id,{role:e.target.value})}><option>MEMBER</option><option>ADMIN</option>{(m.role==='OWNER'||me?.role==='OWNER')&&<option>OWNER</option>}</select></td><td><Button variant="secondary" onClick={()=>change(m.id,{active:!m.active})}>{m.active?'Deactivate':'Activate'}</Button></td><td>{m.role==='ADMIN'&&me?.role==='OWNER'&&<label><input type="checkbox" checked={m.can_manage_admins} onChange={e=>change(m.id,{can_manage_admins:e.target.checked})}/> May manage Admins</label>}</td></tr>)}</tbody></table></div></section>
    <section className="panel review-detail"><h2>Add member</h2><form className="form-stack" onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{setInvitation(await api('/members',{method:'POST',body:JSON.stringify({name:f.get('name'),email:f.get('email'),role:'MEMBER'})}));await load();}catch(err){setError(err.message);}}}><label>Name<input name="name" required minLength={2}/></label><label>Email<input name="email" required type="email"/></label><Button>Add member</Button></form>{invitation&&<p>Share once: {invitation.email} · {invitation.temporary_password}. No invitation email was sent.</p>}</section>
    <section className="panel review-detail"><h2>Audit history</h2>{audit.map(a=><p key={a.id}>{new Date(a.created_at).toLocaleString()} · {a.action} · {a.actor_id} → {a.target_id}<br/>{JSON.stringify(a.details)}</p>)}</section>
  </>;
}
