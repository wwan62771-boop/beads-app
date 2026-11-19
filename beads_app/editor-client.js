(()=>{
 const bar=document.createElement('div');
 bar.style.cssText='position:sticky;top:0;z-index:100;background:#fff8ed;padding:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap';
 const back=document.createElement('a');back.href='/editor';back.textContent='返回云端作品';
 const save=document.createElement('button');save.textContent='保存到云端';save.disabled=true;
 const status=document.createElement('span');status.setAttribute('role','status');
 bar.append(back,save,status);document.body.prepend(bar);
 document.documentElement.style.setProperty('--workshop-bar-height',bar.getBoundingClientRect().height+'px');
 const observer=new ResizeObserver(()=>document.documentElement.style.setProperty('--workshop-bar-height',bar.getBoundingClientRect().height+'px'));observer.observe(bar);
 let bundle,revision,csrf,loaded=false,busy=false;
 const query=new URLSearchParams(location.search),wid=query.get('work'),entry=Number(query.get('entry'));
 async function api(path,body){
  const response=await fetch('/editor-api/'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf||''},body:body?JSON.stringify(body):undefined});
  const result=await response.json();
  if(!response.ok)throw Error(result.error||'云端操作失败。');
  return result;
 }
 function snapshotPNG(doc){return new Promise((resolve,reject)=>{
  rasterExport(doc,'png',blob=>blob.arrayBuffer().then(buffer=>{
   const bytes=new Uint8Array(buffer);let text='';
   for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));
   resolve(btoa(text));
  },reject)).catch(reject);
 })}
 async function initialize(){
  try{
   status.textContent='正在打开可编辑项目…';
   csrf=(await api('session')).csrf;
   const result=await api('works/'+encodeURIComponent(wid));
   bundle=result.bundle;revision=result.revision;
   if(!Number.isInteger(entry)||!bundle.entries[entry])throw Error('请选择有效规格。');
   const project=bundle.entries[entry].project;
   validateProject(project);
   await new Promise((resolve,reject)=>{const image=new Image();image.onload=resolve;image.onerror=()=>reject(Error('项目参考图无法读取。'));image.src=project.reference;});
   const previous=grid;
   loadProject(project);
   const start=Date.now();
   await new Promise((resolve,reject)=>{const timer=setInterval(()=>{
    if(grid!==previous){clearInterval(timer);resolve();}
    else if(Date.now()-start>15000){clearInterval(timer);reject(Error('打开超时，请重新打开作品。'));}
   },50)});
   loaded=true;save.disabled=false;status.textContent='已打开 '+bundle.name+' · 云端第 '+revision+' 版';
  }catch(error){status.textContent=error.message;}
 }
 save.onclick=async()=>{
  if(!loaded||busy)return;
  busy=true;save.disabled=true;status.textContent='正在生成图纸并保存…';
  try{
   const project=JSON.parse(JSON.stringify(projectData())),doc=makeSvg();
   const next=JSON.parse(JSON.stringify(bundle));
   next.entries[entry]={project,png:await snapshotPNG(doc)};
   const result=await api('works/'+encodeURIComponent(wid),{expected_revision:revision,bundle:next});
   revision=result.revision;bundle=next;
   status.textContent='保存成功 · 云端第 '+revision+' 版，可在本机点击“从云端取回”。';
  }catch(error){status.textContent=error.message+' 当前编辑仍在页面，可导出项目保存。';}
  finally{busy=false;save.disabled=false;}
 };
 initialize();
})();
