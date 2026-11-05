import {useEffect,useState} from 'react';
export default function MediaFileInput({accept,required=true}){
  const [file,setFile]=useState(null),[url,setUrl]=useState('');
  useEffect(()=>{if(!file){setUrl('');return;}const value=URL.createObjectURL(file);setUrl(value);return()=>URL.revokeObjectURL(value);},[file]);
  return <><input type="file" name="file" accept={accept} required={required} onChange={e=>setFile(e.target.files?.[0]||null)}/>{url&&(file.type.startsWith('audio/')?<audio controls src={url}/>:file.type.startsWith('video/')?<video controls src={url} style={{maxWidth:'100%',maxHeight:260}}/>:<img src={url} alt="Selected file preview" style={{maxWidth:'100%',maxHeight:260,objectFit:'contain'}}/>)}</>;
}
