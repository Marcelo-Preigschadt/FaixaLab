import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.dirname(here);
const output=process.argv[2];
if(!output)throw Error('Provide the Sites checkout directory.');
const web=path.join(root,'app/faixalab/web');
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'application/javascript; charset=utf-8','.svg':'image/svg+xml','.webmanifest':'application/manifest+json'};
const entries=[];
for(const name of fs.readdirSync(web)){
 const type=types[path.extname(name)];if(!type)continue;
 let body=fs.readFileSync(path.join(web,name),'utf8');
 if(name==='index.html')body=body.replaceAll('Processamento local','Processamento na nuvem').replaceAll('até 1 GB','até 95 MB').replace('</head>','<style>#cloud-connection{position:fixed;z-index:80;right:16px;top:12px;max-width:340px;padding:12px 16px;color:#f5e0b7;background:#29251e;border:1px solid #6d5733;border-radius:10px;font:13px system-ui}#cloud-connection.connected{opacity:0;pointer-events:none;transition:opacity 1s 2s}@media(max-width:640px){#cloud-connection{right:8px;left:68px;max-width:none}}</style><script src="/cloud.js" defer></script></head>');
 entries.push(['/'+name,{body,type}]);
}
entries.push(['/cloud.js',{body:fs.readFileSync(path.join(here,'cloud.js'),'utf8'),type:types['.js']}]);
const metadata=JSON.parse(execFileSync(process.env.FAIXALAB_BUILD_PYTHON||'python3',['-c','import json; from faixalab.chord_dictionary import load_dictionary; from faixalab.instrument_catalog import public_catalog; print(json.dumps({"chords":load_dictionary(),"instruments":public_catalog()}))'],{cwd:root,encoding:'utf8',env:{...process.env,PYTHONPATH:path.join(root,'app')}}));
for(const [route,data] of [['/api/chord-dictionary',metadata.chords],['/api/instruments',metadata.instruments]])entries.push([route,{body:JSON.stringify(data),type:'application/json; charset=utf-8'}]);
const directory=path.resolve(output,'worker');fs.mkdirSync(directory,{recursive:true});
const code=fs.readFileSync(path.join(here,'proxy.mjs'),'utf8')+'\nconst embeddedAssets=new Map('+JSON.stringify(entries)+');\nexport default createGateway({assets:embeddedAssets});\n';
fs.writeFileSync(path.join(directory,'index.js'),code);
console.log(JSON.stringify({assets:entries.length,bytes:Buffer.byteLength(code)}));
