import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import { Button, Notice } from './UI';

const number = value => value == null ? 'Unavailable' : Number(value).toLocaleString(undefined,{maximumFractionDigits:1});
const duration = value => value == null ? 'Unavailable' : `${Math.floor(Math.round(value)/60)}m ${Math.round(value)%60}s`;
function pacificYesterday() {
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const get = type => parts.find(p=>p.type===type).value;
  const date = new Date(`${get('year')}-${get('month')}-${get('day')}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate()-1); return date.toISOString().slice(0,10);
}
function startFor(end,days) { const date = new Date(`${end}T12:00:00Z`); date.setUTCDate(date.getUTCDate()-days+1); return date.toISOString().slice(0,10); }
function Trend({daily,metric,label}) {
  const values = daily.filter(row=>row[metric]!=null), max=Math.max(1,...values.map(row=>row[metric]));
  return <figure className="analytics-trend"><figcaption>{label}</figcaption>{values.length ? <><svg viewBox="0 0 600 140" role="img" aria-label={`${label}: ${values.length} reported days`}><polyline fill="none" stroke="currentColor" strokeWidth="3" points={values.map((row,index)=>`${values.length===1?300:index*580/(values.length-1)+10},${130-row[metric]*115/max}`).join(' ')} />{values.length===1&&<circle cx="300" cy={130-values[0][metric]*115/max} r="4" fill="currentColor" />}</svg><div className="analytics-axis"><span>{values[0].day}</span><span>{values.at(-1).day}</span></div><details><summary>View daily values</summary><table><thead><tr><th>Date</th><th>{label}</th></tr></thead><tbody>{values.map(row=><tr key={row.day}><td>{row.day}</td><td>{number(row[metric])}</td></tr>)}</tbody></table></details></> : <p>No reported daily values. Delayed or unavailable data is not shown as zero.</p>}</figure>;
}

export default function ChannelAnalytics({compact=false}) {
  const [channels,setChannels]=useState(null),[channel,setChannel]=useState(''),[period,setPeriod]=useState('28');
  const [end,setEnd]=useState(pacificYesterday),[start,setStart]=useState(()=>startFor(pacificYesterday(),28));
  const [result,setResult]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[refresh,setRefresh]=useState(0);
  const sequence=useRef(0), manual=useRef(false), displayed=useRef('');
  useEffect(()=>{ const controller=new AbortController(); let live=true; api('/analytics/channels',{signal:controller.signal}).then(data=>{if(!live)return;setChannels(data);setChannel(data.find(c=>c.connection==='connected')?.id || data[0]?.id || '');}).catch(e=>{if(live&&e.name!=='AbortError')setError(e.message);});return()=>{live=false;controller.abort();}; },[]);
  useEffect(()=>{
    if(!channel)return;
    const version=++sequence.current, controller=new AbortController(); let timer;
    const identity=`${channel}:${start}:${end}`;
    if(displayed.current!==identity){setResult(null);displayed.current=identity;}
    setError('');setLoading(true);
    const forced=manual.current;manual.current=false;
    async function load(force=false) {
      try {
        const data=await api(`/analytics/channels/${encodeURIComponent(channel)}?start_date=${start}&end_date=${end}${force?'&refresh=true':''}`,{signal:controller.signal});
        if(version!==sequence.current)return;
        setResult(data);setError('');setLoading(false);
        if(data.state==='loading')timer=setTimeout(()=>load(),2000);
      } catch(e) {if(version===sequence.current&&e.name!=='AbortError'){setError(e.message);setLoading(false);}}
    }
    load(forced);
    return()=>{sequence.current++;controller.abort();clearTimeout(timer);};
  },[channel,start,end,refresh]);
  const selected=channels?.find(c=>c.id===channel), totals=result?.data?.totals;
  function changePeriod(value) {setPeriod(value);if(value!=='custom'){const last=pacificYesterday();setEnd(last);setStart(startFor(last,Number(value)));}}
  async function connect(){try{const data=await api('/youtube/connect');window.location.assign(data.authorization_url);}catch(e){setError(e.message);}}
  return <section className="panel channel-analytics" aria-label="YouTube channel analytics"><div className="analytics-heading"><div><h2>{compact?'Channel performance':'YouTube Analytics'}</h2><p className="muted">Selected-period reports for all channel videos, including uploads outside AI Shorts.</p></div>{compact&&<Link to="/analytics">View analytics →</Link>}</div>
    <div className="analytics-controls"><label>Channel<select aria-label="Analytics channel" value={channel} onChange={e=>setChannel(e.target.value)} disabled={!channels?.length}>{!channels?.length&&<option>No channels</option>}{channels?.map(c=><option key={c.id} value={c.id}>{c.name}{c.connection!=='connected'?' · connection required':''}</option>)}</select></label>{!compact&&<><label>Period<select aria-label="Analytics period" value={period} onChange={e=>changePeriod(e.target.value)}><option value="7">Last 7 days</option><option value="28">Last 28 days</option><option value="90">Last 90 days</option><option value="custom">Custom dates</option></select></label>{period==='custom'&&<><label>From<input aria-label="Analytics start date" type="date" value={start} max={end} onChange={e=>setStart(e.target.value)} /></label><label>Through<input aria-label="Analytics end date" type="date" value={end} min={start} max={pacificYesterday()} onChange={e=>setEnd(e.target.value)} /></label></>}</>}<Button disabled={loading||!channel} onClick={()=>{manual.current=true;setRefresh(n=>n+1);}}>Refresh</Button></div>
    {selected&&<div className="analytics-channel">{selected.avatar&&<img src={selected.avatar} alt="" referrerPolicy="no-referrer" />}<strong>{selected.name}</strong></div>}
    <Notice>{error || result?.error}</Notice>
    {!channels&&!error&&<p role="status">Loading authorized channels…</p>}
    {channels?.length===0&&<p>No channels yet. <Link to="/channels">Connect a YouTube channel</Link> to inspect its reports.</p>}
    {loading&&<p role="status">Loading channel reports…</p>}
    {result&&['not_connected','missing_permission','reconnect'].includes(result.state)&&<div className="analytics-setup"><strong>{result.state==='missing_permission'?'Reconnect for analytics':result.state==='reconnect'?'YouTube connection expired':'No OAuth connection'}</strong><p>{result.message} Manual/demo channels do not contain live analytics.</p>{selected?.can_connect?<Button onClick={connect}>Connect analytics</Button>:<p>Ask this channel’s authorizing member to reconnect from Channels.</p>}</div>}
    {result?.stale&&result.data&&<p role="status">Cached report · stale{result.error?' because refresh failed':''}. Last successful data remains visible.</p>}
    {result?.data&&<><div className="analytics-metrics">{[['Views',totals?.views],['Watch time (hours)',totals?.watch_hours],['Average view duration',duration(totals?.averageViewDuration)],...(!compact?[['Subscribers gained',totals?.subscribersGained],['Subscribers lost',totals?.subscribersLost],['Engaged views',totals?.engagedViews]]:[])].map(([label,value])=><div className="analytics-metric" key={label}><span>{label}</span><strong>{typeof value==='string'?value:number(value)}</strong></div>)}</div>{!totals&&<p>No reported activity data for this period. YouTube may withhold or delay reports; missing values are not zero.</p>}
    {!compact&&<><div className="analytics-charts"><Trend daily={result.data.daily} metric="views" label="Daily views" /><Trend daily={result.data.daily} metric="watch_hours" label="Daily watch time (hours)" /></div><h3>Top 10 videos · selected period</h3><div className="analytics-videos">{result.data.videos.map(video=><article key={video.video}>{video.thumbnail&&<img src={video.thumbnail} alt="" referrerPolicy="no-referrer" />}<a href={`https://www.youtube.com/watch?v=${encodeURIComponent(video.video)}`} target="_blank" rel="noreferrer">{video.title}</a><span>{number(video.views)} views</span><span>{number(video.watch_hours)} watch hours</span><span>{duration(video.averageViewDuration)} average</span></article>)}{!result.data.videos.length&&<p>No top-video rows available for this period.</p>}</div></>}
    <p className="analytics-footnote">{result.start_date} – {result.end_date} · Last successful sync: {result.synced_at?new Date(result.synced_at).toLocaleString():'Unavailable'} · Latest reported day: {result.data.latest_reporting_date || 'Unavailable'}</p></>}
    <p className="analytics-footnote">Dates use Pacific time. Reporting can be delayed and is not real-time. Views and engaged views are distinct. Watch time is ordinary viewing time, not monetization-eligible public watch hours.</p>
  </section>;
}
