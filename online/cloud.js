'use strict';
document.addEventListener('DOMContentLoaded',()=>{
 const notice=document.createElement('aside');notice.id='cloud-connection';notice.setAttribute('role','status');notice.textContent='Verificando o processamento na nuvem…';document.body.append(notice);
 let maximum=95*1024*1024;
 async function check(){
  let connected=false;
  try{
   const response=await fetch('/api/cloud/status',{signal:AbortSignal.timeout(10000),cache:'no-store'}),status=await response.json();
   connected=response.ok&&status.connected;maximum=status.max_upload_bytes||maximum;
   notice.textContent=connected?'Processamento na nuvem conectado':status.detail||'Servidor de IA indisponível.';
  }catch{notice.textContent='Sem conexão com o processamento. Verifique sua internet e tente novamente.';}
  notice.classList.toggle('connected',connected);
  const indicator=document.querySelector('.status-dot');if(indicator)indicator.style.background=connected?'#00c4ce':'#af996c';
  for(const id of ['new-project','start-import']){const button=document.getElementById(id);if(button)button.disabled=!connected;}
 }
 document.addEventListener('change',event=>{
  if(event.target.type!=='file')return;
  const file=event.target.files?.[0];
  if(file&&file.size>maximum){event.target.value='';notice.textContent='No site, escolha um MP3 de até 95 MB.';event.stopImmediatePropagation();}
 },true);
 check();setInterval(check,30000);
});
