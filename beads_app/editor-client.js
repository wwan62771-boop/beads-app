(()=>{
 const bar=document.createElement('div');
 bar.style.cssText='position:sticky;top:0;z-index:100;background:#fff8ed;padding:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap';
 const back=document.createElement('a');back.href='/editor';back.textContent='返回云端作品';
 const save=document.createElement('button');save.textContent='保存到云端';save.disabled=true;
 const nameLabel=document.createElement('label');nameLabel.textContent='作品名称 ';
 const nameInput=document.createElement('input');nameInput.maxLength=120;nameInput.placeholder='给新图纸起个名字';nameLabel.append(nameInput);
 const seriesLabel=document.createElement('label');seriesLabel.textContent='系列名称 ';
 const seriesInput=document.createElement('input');seriesInput.maxLength=120;seriesInput.placeholder='可选';seriesLabel.append(seriesInput);
 const status=document.createElement('span');status.setAttribute('role','status');
 bar.append(back,nameLabel,seriesLabel,save,status);document.body.prepend(bar);
 document.documentElement.style.setProperty('--workshop-bar-height',bar.getBoundingClientRect().height+'px');
 const observer=new ResizeObserver(()=>document.documentElement.style.setProperty('--workshop-bar-height',bar.getBoundingClientRect().height+'px'));observer.observe(bar);
 let bundle,revision=0,csrf,loaded=false,busy=false,pending=null;
 const query=new URLSearchParams(location.search);
 let wid=query.get('work'),entry=Number(query.get('entry')),isNew=query.get('new')==='1';
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
 function syncSaveButton(){save.disabled=!loaded||busy||!grid.length;}
 async function initialize(){
  try{
   csrf=(await api('session')).csrf;
   if(isNew){
    wid=crypto.randomUUID().replaceAll('-','');
    entry=0;
    bundle={format:'wanwan-editable-work-v1',name:'',series:'',entries:[]};
    loaded=true;syncSaveButton();
    status.textContent='请上传底图后生成图纸，或展开“新建画布”自定义绘制。';
    return;
   }
   nameLabel.style.display='none';seriesLabel.style.display='none';
   status.textContent='正在打开可编辑项目…';
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
   loaded=true;syncSaveButton();status.textContent='已打开 '+bundle.name+' · 云端第 '+revision+' 版';
  }catch(error){status.textContent=error.message;}
 }
 const oldUpdate=update;
 update=function(){oldUpdate();syncSaveButton();};
 save.onclick=async()=>{
  if(!loaded||busy||!grid.length)return;
  if(isNew&&!nameInput.value.trim()){status.textContent='请先填写作品名称。';nameInput.focus();return;}
  busy=true;syncSaveButton();status.textContent='正在生成图纸并保存…';
  nameInput.disabled=true;seriesInput.disabled=true;
  try{
   // Recover a lost save response before creating another revision.
   if(pending){
    const remote=await api('works/'+encodeURIComponent(wid)).catch(()=>null);
    if(remote&&JSON.stringify(remote.bundle)===JSON.stringify(pending)){
     bundle=remote.bundle;revision=remote.revision;pending=null;
    }
   }
   const project=JSON.parse(JSON.stringify(projectData())),doc=makeSvg();
   if(isNew)project.name=nameInput.value.trim();
   const next=JSON.parse(JSON.stringify(bundle));
   if(isNew){next.name=nameInput.value.trim();next.series=seriesInput.value.trim()||'云端新作品';}
   next.entries[entry]={project,png:await snapshotPNG(doc)};
   pending=next;
   const result=await api('works/'+encodeURIComponent(wid),{expected_revision:revision,bundle:next});
   revision=result.revision;bundle=next;pending=null;isNew=false;
   nameLabel.style.display='none';seriesLabel.style.display='none';
   history.replaceState(null,'','/editor/workshop?work='+encodeURIComponent(wid)+'&entry='+entry);
   status.textContent='保存成功 · '+bundle.name+' · 云端第 '+revision+' 版，可在本机点击“从云端取回”。';
  }catch(error){status.textContent=error.message+' 当前编辑仍在页面，可导出项目保存。';}
  finally{busy=false;nameInput.disabled=false;seriesInput.disabled=false;syncSaveButton();}
 };
 initialize();
})();
