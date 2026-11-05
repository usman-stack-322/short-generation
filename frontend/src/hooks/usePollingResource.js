import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';

// Poll serially: no overlapping polls, no old-route response updates, and no
// in-flight poll overwriting a newer local mutation/action response.
export function usePollingResource(path, interval=2500) {
  const [state,setState]=useState({path,data:null,loaded:false,error:''});
  const active=useRef(null),epoch=useRef(0);
  useEffect(()=>{
    const token={path,live:true};active.current=token;epoch.current++;
    let timer,controller;
    setState({path,data:null,loaded:false,error:''});
    async function load(){
      const version=epoch.current;controller=new AbortController();
      try{
        const data=await api(path,{signal:controller.signal});
        if(token.live&&version===epoch.current)setState({path,data,loaded:true,error:''});
      }catch(error){
        if(token.live&&version===epoch.current&&error.name!=='AbortError')
          setState(old=>({...old,error:error.message}));
      }finally{if(token.live)timer=setTimeout(load,interval);}
    }
    load();
    return()=>{token.live=false;clearTimeout(timer);controller?.abort();};
  },[path,interval]);
  const setData=useCallback(next=>{
    if(!active.current?.live||active.current.path!==path)return;
    epoch.current++;
    setState(old=>old.path===path?{...old,data:typeof next==='function'?next(old.data):next,loaded:true}:old);
  },[path]);
  return state.path===path?{...state,setData}:{data:null,loaded:false,error:'',setData};
}
