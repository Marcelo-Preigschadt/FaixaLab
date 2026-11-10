// The browser never receives the processing server's key. The gateway streams
// files and byte ranges; it does not load a whole music file into Worker memory.
export function createGateway({assets=new Map(),fetcher=fetch}={}) {
 const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}});
 function backend(env) {
  if(!env.FAIXALAB_BACKEND_URL||!env.FAIXALAB_BACKEND_KEY)return null;
  const url=new URL(env.FAIXALAB_BACKEND_URL);
  if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.pathname!=='/'||(url.port&&url.port!=='443'))throw Error('Invalid processing origin');
  return url;
 }
 return {async fetch(request,env={}) {
  const url=new URL(request.url);
  if(url.pathname.startsWith('/api/')&&!request.headers.get('oai-authenticated-user-id'))return json({detail:'Entre na sua conta para abrir o FaixaLab.'},401);
  if(!url.pathname.startsWith('/api/')||assets.has(url.pathname)) {
   const entry=assets.get(url.pathname==='/'?'/index.html':url.pathname);
   if(!entry)return new Response('Não encontrado.',{status:404});
   return new Response(request.method==='HEAD'?null:entry.body,{headers:{'Content-Type':entry.type,'Cache-Control':url.pathname==='/service-worker.js'?'no-cache':'public, max-age=0, must-revalidate','X-Content-Type-Options':'nosniff'}});
  }
  let origin;
  try{origin=backend(env);}catch{return json({detail:'A conexão do servidor precisa ser corrigida.'},503);}
  if(!origin)return json({connected:false,reason:'not_configured',detail:'O site está preparado; o servidor de IA ainda não foi conectado.'},503);
  const mutating=!['GET','HEAD'].includes(request.method);
  if(mutating&&request.headers.get('origin')&&request.headers.get('origin')!==url.origin)return json({detail:'Origem não autorizada.'},403);
  const maximum=95*1024*1024;
  if(Number(request.headers.get('content-length'))>maximum)return json({detail:'No site, envie um MP3 de até 95 MB.'},413);
  const target=new URL(url.pathname==='/api/cloud/status'?'/api/connection':url.pathname+url.search,origin);
  const headers=new Headers();
  for(const name of ['content-type','content-length','range','if-range','if-none-match','if-modified-since'])if(request.headers.has(name))headers.set(name,request.headers.get(name));
  headers.set('x-faixalab-key',env.FAIXALAB_BACKEND_KEY);
  if(mutating)headers.set('origin',origin.origin);
  try {
   const statusRequest=url.pathname==='/api/cloud/status';
   const init={method:statusRequest?'GET':request.method,headers,redirect:'manual'};
   if(mutating&&request.body){init.body=request.body;init.duplex='half';}
   if(statusRequest)init.signal=AbortSignal.timeout(8000);
   const response=await fetcher(target,init);
   if(response.status>=300&&response.status<400&&response.status!==304)return json({detail:'O endereço do servidor redirecionou a conexão. Confira a configuração.'},502);
   if(statusRequest){
    if(response.status===401)return json({connected:false,reason:'unauthorized',detail:'A autenticação do servidor precisa ser ajustada.'},503);
    if(!response.ok)return json({connected:false,reason:'unavailable',detail:'O servidor de IA não está disponível.'},503);
    const health=await response.json();
    if(health.status!=='ok')return json({connected:false,reason:'unavailable',detail:'O processamento ainda não está pronto.'},503);
    return json({connected:true,version:health.version,processing:health.processing,max_upload_bytes:maximum});
   }
   const resultHeaders=new Headers();
   for(const name of ['content-type','content-length','content-range','accept-ranges','content-disposition','etag','last-modified','retry-after'])if(response.headers.has(name))resultHeaders.set(name,response.headers.get(name));
   resultHeaders.set('Cache-Control',url.pathname.includes('/audio/')?'private, max-age=31536000, immutable':'private, no-store');
   return new Response(response.body,{status:response.status,headers:resultHeaders});
  }catch{return json({connected:false,reason:'unavailable',detail:'Não foi possível conectar ao servidor de IA. Ele pode estar iniciando ou suspenso.'},503);}
 }};
}
