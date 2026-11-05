import ChannelAnalytics from "../components/ChannelAnalytics";

import { ArrowDownRight, ArrowUpRight, ArrowRight, CheckCircle2, CircleAlert, Clock3, Clapperboard, Plus, Radio, Sparkles, Video } from "lucide-react";
import { Link } from "react-router-dom";
import { mediaUrl } from "../services/api";
import { EmptyState, PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";
import { usePollingResource } from '../hooks/usePollingResource';

const metricIcons = [Radio, Video, Clock3, CheckCircle2, ArrowUpRight, CircleAlert];
const statusLabel = (status) => status?.replaceAll("_", " ") || "Queued";

export default function Dashboard() {
  const {data,error} = usePollingResource('/dashboard',5000);
  if (!data && !error) return <Loading />;
  const owner = data?.role === "OWNER";
  const metrics = [
    ['Ready for Review',data?.waiting_approval??0,'Current rendered content','green'],
    ['Needs Attention',data?.needs_attention??0,'Research holds and failed stages','orange'],
    ['Scheduled Today',data?.scheduled_today??0,'UTC schedule','purple'],
    ['Processing',data?.processing??0,'Active research, generation and render stages','blue'],
  ];
  return <><PageHeader eyebrow="YOUR CREATOR WORKSPACE" title={owner ? "Workspace Dashboard" : "My Dashboard"} description={owner ? "Activity across your workspace." : "Your channels, themes and video activity."} action={<Link to="/title-to-short"><Button><Plus size={16} /> Create a Short</Button></Link>} /><Notice>{error}</Notice>
    <div className="metric-grid operational-metrics">{metrics.map(([label, value, sub, color], index) => { const Icon = metricIcons[index % metricIcons.length]; return <div className="metric-card" key={label}><div className="metric-top"><span>{label}</span><span className={`metric-icon ${color}`}><Icon size={17} /></span></div><strong>{value}</strong><small>{sub}</small></div>; })}</div>
    <section className="panel review-detail"><h2>Run sheet</h2><p>{data?.automation_state}</p><p>Research / Script / Voice / Media / Render / Review / Schedule / Upload. Times shown in your device timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone}); schedule totals above use UTC.</p>{data?.run_sheet?.length?<div className="table-wrap"><table><thead><tr><th>Channel / Topic</th><th>Stage</th><th>Scheduled</th><th>Next action</th></tr></thead><tbody>{data.run_sheet.map(j=><tr key={j.id}><td>{j.channel_name}<br/>{j.topic||'Research pending'}</td><td>{statusLabel(j.status)}{j.failed_step&&<small> / {statusLabel(j.failed_step)}</small>}</td><td>{j.upload?.scheduled_at?`${new Date(j.upload.scheduled_at).toLocaleString()} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`:'Not scheduled'}</td><td><Link className="text-link" to={`/videos/${j.id}`}>{j.status==='verification_required'?'Retry Research':j.failed_step==='voice_generation'?'Retry Voice':j.failed_step==='collecting_assets'?'Choose Saved Photos':j.status==='ready_for_review'?'Review Short':'Open job'}</Link>{j.error_message&&<details><summary>Needs attention</summary><p>{j.error_message}</p></details>}</td></tr>)}</tbody></table></div>:<p>No runnable jobs yet. Add a channel, assign a personality and create a Short.</p>}</section>
    <ChannelAnalytics compact />
    {owner && <section className="panel team-activity"><h2>Team activity</h2><div className="table-wrap"><table><thead><tr><th>Member</th><th>Channels</th><th>Videos today</th><th>Current jobs</th><th>Failed</th><th>Recent activity</th><th>Last active</th></tr></thead><tbody>{data?.team_activity?.map((row,index)=><tr key={index}><td>{row.member}</td><td>{row.channels.join(', ') || 'No assigned channel'}</td><td>{row.videos_today}</td><td>{row.current_jobs}</td><td>{row.failed_jobs}</td><td>{row.recent_activity ? new Date(row.recent_activity).toLocaleString() : 'No jobs yet'}</td><td>{row.last_active ? new Date(row.last_active).toLocaleString() : 'Not recorded'}</td></tr>)}</tbody></table></div></section>}
    <div className="dashboard-grid">
      <section className="panel recent-panel"><div className="panel-heading"><div><h2>Recent videos</h2><p>Your latest creations and updates</p></div><Link className="text-link" to="/videos">View queue <ArrowRight size={14} /></Link></div>
        {data?.recent_videos?.length ? <div className="table-wrap"><table><thead><tr><th>VIDEO</th><th>CHANNEL</th><th>STATUS</th><th>CREATED</th><th /></tr></thead><tbody>{data.recent_videos.slice(0, 5).map((video) => <tr key={video.id}><td><div className="video-cell"><img src={mediaUrl(video.thumbnail_url) || "/cover-placeholder.svg"} onError={(event) => { event.currentTarget.src = "/cover-placeholder.svg"; }} alt="" /><span><strong>{video.seo?.title || video.topic}</strong><small>{video.personality_name} · {video.duration}s</small></span></div></td><td>{video.channel_name}</td><td><span className={`status-pill status-${video.status}`}>{statusLabel(video.status)}</span></td><td>{video.created_at ? new Date(video.created_at).toLocaleDateString() : "—"}</td><td><Link className="row-arrow" to={`/videos/${video.id}`}>↗</Link></td></tr>)}</tbody></table></div> : <EmptyState title="Your first Short is waiting" detail="Choose a channel and a story to create your first video." action={<Link className="text-link" to="/title-to-short">Create a Short <ArrowRight size={14} /></Link>} />}
      </section>
      <aside className="dashboard-side"><section className="panel side-panel"><div className="panel-heading"><div><h2>Channel status</h2><p>Your connected channels</p></div><Link to="/channels" className="icon-link"><ArrowRight size={15} /></Link></div>{data?.channels?.length ? <div className="channel-list">{data.channels.slice(0, 4).map((channel) => <div className="channel-row" key={channel.id}><div className="channel-avatar"><span>{channel.name.slice(0, 1)}</span><i /></div><div><strong>{channel.name}</strong><small>{channel.status.replaceAll("_"," ")} · {channel.member_name}</small><small>{channel.active_personality || "No assigned theme"} · {channel.videos_today}/{channel.daily_video_target} today</small><small>Approval: {channel.approval_policy.replaceAll("_"," ")}{channel.next_scheduled && ` · Next ${new Date(channel.next_scheduled).toLocaleString()}`}</small></div><span className="connection-dot" /></div>)}</div> : <p className="side-empty">Add a channel to get started.</p>}<Link className="side-footer-link" to="/channels">Manage channels <ArrowRight size={13} /></Link></section>
        <section className="panel side-panel personality-panel"><div className="panel-heading"><div><h2>Active personalities</h2><p>Your content themes</p></div><Sparkles size={16} className="purple-text" /></div>{data?.active_personalities?.length ? <div className="personality-list">{data.active_personalities.slice(0, 3).map((personality, index) => <div className="personality-row" key={personality.id}><div className={`personality-avatar tone-${index}`}>{personality.name.slice(0, 1)}</div><div><strong>{personality.name}</strong><small>{personality.category}</small></div><span className="personality-active">Active</span></div>)}</div> : <p className="side-empty">Add a personality to shape your stories.</p>}<Link className="side-footer-link" to="/personalities">Manage personalities <ArrowRight size={13} /></Link></section>
        <div className="tip-card"><div className="tip-head"><span><Sparkles size={15} /></span><strong>Creator tip</strong><span className="tip-stars">✦ ✧</span></div><p>A great hook earns the next second. Start with a surprising question or a detail that makes people curious.</p><Link to="/title-to-short">Try it out <ArrowRight size={13} /></Link></div>
      </aside>
    </div>
  </>;
}

