'use strict';
const http  = require('http');
const https = require('https');
const fs    = require('fs');
const path  = require('path');
const url   = require('url');
const { buildResumePDF } = require('./pdf_builder');

const cfgPath = path.join(__dirname, 'config.json');
function loadCfg() {
  try { return JSON.parse(fs.readFileSync(cfgPath,'utf8')); }
  catch { return { port:3747, anthropicKey:'' }; }
}
const PORT = loadCfg().port || 3747;
const CORS = {
  'Access-Control-Allow-Origin':'*',
  'Access-Control-Allow-Methods':'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers':'Content-Type'
};
function getKey() { return loadCfg().anthropicKey || process.env.ANTHROPIC_API_KEY || ''; }
function readBody(req) {
  return new Promise((res,rej)=>{
    let b='';
    req.on('data',c=>b+=c);
    req.on('end',()=>{ try{res(JSON.parse(b));}catch(e){rej(e);} });
    req.on('error',rej);
  });
}
function httpsPost(host,p,headers,body) {
  return new Promise((resolve,reject)=>{
    const data=JSON.stringify(body);
    const req=https.request({method:'POST',hostname:host,path:p,
      headers:{'Content-Type':'application/json','Content-Length':Buffer.byteLength(data),...headers}},
      res=>{let d='';res.on('data',c=>d+=c);res.on('end',()=>{try{resolve({status:res.statusCode,body:JSON.parse(d)});}catch(e){reject(new Error('Bad JSON: '+d.slice(0,200)));} });});
    req.on('error',reject);req.write(data);req.end();
  });
}
function send(res,status,obj) {
  res.writeHead(status,{'Content-Type':'application/json',...CORS});
  res.end(JSON.stringify(obj));
}

const server = http.createServer(async(req,res)=>{
  const {pathname}=url.parse(req.url);
  if(req.method==='OPTIONS'){res.writeHead(204,CORS);res.end();return;}

  if(req.method==='GET'&&(pathname==='/'||pathname==='/index.html')){
    try{res.writeHead(200,{'Content-Type':'text/html;charset=utf-8',...CORS});res.end(fs.readFileSync(path.join(__dirname,'index.html'),'utf8'));}
    catch(e){send(res,500,{error:'index.html missing'});}
    return;
  }
  if(req.method==='GET'&&pathname==='/api/config'){
    const key=getKey();
    send(res,200,{hasKey:!!key,keyPreview:key?key.slice(0,16)+'...':'',port:PORT});
    return;
  }
  if(req.method==='POST'&&pathname==='/api/save-config'){
    try{
      const inc=await readBody(req);
      fs.writeFileSync(cfgPath,JSON.stringify({...loadCfg(),...inc},null,2));
      console.log('[config] key saved:',inc.anthropicKey?inc.anthropicKey.slice(0,16)+'...':'none');
      send(res,200,{ok:true});
    }catch(e){send(res,500,{error:e.message});}
    return;
  }
  if(req.method==='POST'&&pathname==='/api/claude'){
    const key=getKey();
    if(!key){send(res,400,{type:'error',error:{type:'no_key',message:'No API key. Add one in Setup.'}});return;}
    try{
      const payload=await readBody(req);
      console.log('[claude] key:',key.slice(0,16)+'...');
      const result=await httpsPost('api.anthropic.com','/v1/messages',
        {'x-api-key':key,'anthropic-version':'2023-06-01'},payload);
      console.log('[claude] status:',result.status,result.body.type==='error'?'ERR:'+result.body.error?.message:'OK');
      res.writeHead(result.status,{'Content-Type':'application/json',...CORS});
      res.end(JSON.stringify(result.body));
    }catch(e){send(res,500,{type:'error',error:{type:'server_error',message:e.message}});}
    return;
  }
  if(req.method==='POST'&&pathname==='/api/generate-pdf'){
    try{
      const data=await readBody(req);
      const buf=buildResumePDF(data);
      res.writeHead(200,{'Content-Type':'application/pdf',
        'Content-Disposition':'attachment; filename="resume.pdf"',
        'Content-Length':buf.length,...CORS});
      res.end(buf);
    }catch(e){
      console.error('[pdf]',e.message);
      send(res,500,{error:'PDF failed: '+e.message});
    }
    return;
  }
  res.writeHead(404,CORS);res.end('Not found');
});

server.on('error',e=>{
  if(e.code==='EADDRINUSE'){console.log('\n  Port '+PORT+' already in use — open http://localhost:'+PORT);}
  else console.error('Server error:',e.message);
  process.exit(0);
});
server.listen(PORT,'127.0.0.1',()=>{
  const key=getKey();
  console.log('\n  DevOps Job Hub → http://localhost:'+PORT);
  console.log('  API key:',key?key.slice(0,16)+'... ✓':'NOT SET');
  console.log('  PDF: built-in (no dependencies)\n');
  try{const cmd=process.platform==='darwin'?'open':process.platform==='win32'?'start':'xdg-open';require('child_process').exec(cmd+' http://localhost:'+PORT);}catch{}
});
