/* Fabric.js interaction only: document JSON + DOM remain the rendering source. */
window.LayerControls=class {
  constructor(host,update,select){
    const el=document.createElement('canvas');host.append(el);
    this.canvas=new fabric.Canvas(el,{selection:false,enableRetinaScaling:true,preserveObjectStacking:true});
    this.update=update;this.select=select;this.syncing=false;
    for(const event of ['selection:created','selection:updated'])this.canvas.on(event,e=>{if(!this.syncing&&e.selected?.[0]){const o=e.selected[0];select(o.collection,o.layerId);}});
    for(const event of ['object:moving','object:scaling','object:modified'])this.canvas.on(event,e=>{
      if(this.syncing)return;const o=e.target;
      const w=Math.max(1,Math.min(this.width,o.width*o.scaleX)),h=Math.max(1,Math.min(this.height,o.height*o.scaleY));
      const box={x:Math.round(Math.max(0,Math.min(this.width-w,o.left))),y:Math.round(Math.max(0,Math.min(this.height-h,o.top))),width:Math.floor(w),height:Math.floor(h)};
      o.set({left:box.x,top:box.y,width:box.width,height:box.height,scaleX:1,scaleY:1});o.setCoords();
      update(o.collection,o.layerId,box);
    });
  }
  sync(doc,cut,scale,selected,paint){
    this.syncing=true;this.width=doc.width;this.height=doc.height;
    const c=this.canvas;c.clear();c.setDimensions({width:Math.round(doc.width*scale),height:Math.round(doc.height*scale)});c.setViewportTransform([scale,0,0,scale,0,0]);c.skipTargetFind=paint;
    for(const collection of ['masks','texts'])for(const t of cut[collection]){
      const o=new fabric.Rect({left:t.x,top:t.y,width:t.width,height:t.height,fill:'rgba(36,120,91,0.015)',stroke:collection==='texts'?'#24785b':'#d88726',strokeWidth:1/scale,strokeDashArray:[5/scale,4/scale],strokeUniform:true,cornerColor:'#24785b',transparentCorners:false,cornerSize:11,padding:0,lockRotation:true,lockScalingFlip:true,hasRotatingPoint:false,selectable:!paint,objectCaching:false});
      o.setControlsVisibility({mtr:false});o.collection=collection;o.layerId=t.id;c.add(o);
      if(selected?.id===t.id&&selected.collection===collection&&!paint)c.setActiveObject(o);
    }
    c.requestRenderAll();this.syncing=false;
  }
  activate(collection,id){const o=this.canvas.getObjects().find(o=>o.collection===collection&&o.layerId===id);if(o&&this.canvas.getActiveObject()!==o){this.syncing=true;this.canvas.setActiveObject(o);this.canvas.requestRenderAll();this.syncing=false;}}
};
