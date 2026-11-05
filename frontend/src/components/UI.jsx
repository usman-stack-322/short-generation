import { LoaderCircle } from "lucide-react";
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

export function Button({ children, loading, variant = "primary", className = "", disabled, ...props }) {
  return <button className={`button button-${variant} ${className}`} disabled={disabled || loading} {...props}>{loading && <LoaderCircle className="spin" size={16} />}{children}</button>;
}

export function Loading() {
  return <div className="loading"><LoaderCircle className="spin" size={19} /> Loading your workspace…</div>;
}

export function Notice({ type = "error", children }) {
  return children ? <div role={type==='error'?'alert':'status'} className={`notice notice-${type}`}>{type==='error' ? <><strong>We couldn’t complete this request.</strong><p>Check your connection and try again. Workspace data already saved is preserved.</p><details><summary>Technical details</summary><div className="job-log">{children}</div></details></> : children}</div> : null;
}

export function Modal({ title, onClose, children }) {
  const dialog=useRef(null);
  const closeRef=useRef(onClose);
  closeRef.current=onClose;
  useEffect(()=>{
    const previous=document.activeElement;
    const element=dialog.current;
    const controls=()=>[...element.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]')];
    controls()[0]?.focus();
    function key(event){
      if(event.key==='Escape')closeRef.current();
      if(event.key==='Tab'){
        const nodes=controls(),first=nodes[0],last=nodes.at(-1);
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
      }
    }
    element.addEventListener('keydown',key);
    return()=>{element.removeEventListener('keydown',key);previous?.focus();};
  },[]);
  return createPortal(<div className="modal-backdrop" role="presentation" onMouseDown={onClose}><div ref={dialog} className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}><div className="modal-title"><h2>{title}</h2><button type="button" className="icon-button" onClick={onClose} aria-label="Close">×</button></div>{children}</div></div>, document.body);
}
