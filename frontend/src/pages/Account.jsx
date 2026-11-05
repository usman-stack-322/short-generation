import {useEffect,useState} from 'react';
import {api} from '../services/api';
import {PageHeader} from '../components/Shell';
import {Notice} from '../components/UI';
export default function Account(){
  const [me,setMe]=useState(null),[error,setError]=useState('');
  useEffect(()=>{api('/auth/me').then(setMe).catch(e=>setError(e.message));},[]);
  return <><PageHeader title="Account Settings" description="Your personal workspace and account access."/><Notice>{error}</Notice>{me&&<section className="panel review-detail"><h2>{me.name}</h2><p>{me.email}</p><p>Access: {me.role}</p><p>Your channels, imported media, research and videos remain private to your account.</p><p>Connect channels with Google OAuth under My Channels. Google passwords are never requested.</p></section>}</>;
}
