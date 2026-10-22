/* One DOM renderer shared by preview, editable HTML and PNG export. */
window.TextLayers={
 async mount(doc,cut){
  const generation=this.generation=(this.generation||0)+1;window.renderResult={ready:false};window.renderError=null;
  const board=document.getElementById('artboard');board.replaceChildren();board.style.width=doc.width+'px';board.style.height=doc.height+'px';board.style.background=cut.background_color;
  if(cut.background){let im=document.createElement('img');im.src=doc.assets[cut.background].path;im.className='background';im.draggable=false;board.append(im);await im.decode();}
  if(generation!==this.generation)return {ready:false,metrics:[]};
  for(const m of cut.masks){let el=document.createElement('div');el.className='mask';el.dataset.id=m.id;Object.assign(el.style,{left:m.x+'px',top:m.y+'px',width:m.width+'px',height:m.height+'px',background:m.color});board.append(el);}
  for(const t of cut.texts){let el=document.createElement('div');el.className='text';el.dataset.id=t.id;el.textContent=t.text;Object.assign(el.style,{left:t.x+'px',top:t.y+'px',width:t.width+'px',height:t.height+'px',fontSize:t.font_size+'px',fontWeight:String(t.weight),color:t.color,textAlign:t.align,lineHeight:String(t.line_height)});board.append(el);}
  await document.fonts.load('24px LayerSans','한글');await document.fonts.load('700 24px LayerSans','한글');await document.fonts.ready;
  if(generation!==this.generation)return {ready:false,metrics:[]};
  if(!document.fonts.check('24px LayerSans','한글'))throw Error('Bundled Korean font failed to load');
  let metrics=[];
  for(const t of cut.texts){let el=board.querySelector('[data-id="'+t.id+'"]');let n=t.font_size;
   if(t.auto_fit){while(n>t.min_font_size&&(el.scrollHeight>t.height+1||el.scrollWidth>t.width+1)){n--;el.style.fontSize=n+'px';}}
   metrics.push({id:t.id,text:el.textContent,font_size:n,overflow:el.scrollHeight>t.height+1||el.scrollWidth>t.width+1});
  }
  window.renderResult={ready:true,metrics};return window.renderResult;
 }
};
