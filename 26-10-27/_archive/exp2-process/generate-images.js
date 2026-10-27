async (page) => {
  const root='/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault/26-10-27/exp2-perplexity/evidence-01';
  const manifests=[];
  for (const font of [16,24,32,40,64]) {
    for (let gray=1;gray<=32;gray++) {
      await page.waitForTimeout(250);
      const result=await page.evaluate(({font,gray})=>{
        setFont(font);setGray(gray);
        return {invalid:state.invalid,text:params().text,bounds:state.bounds};
      },{font,gray});
      if(result.invalid || result.text.split('\n').length!==5 || result.text.replace(/\s/g,'').length!==100) throw new Error('Invalid layout');
      const id=`f${font}-g${String(gray).padStart(2,'0')}`;
      const pending=page.waitForEvent('download');
      await page.evaluate(()=>exportPng());
      await(await pending).saveAs(`${root}/source-images/${id}.png`);
      const metadata=await page.evaluate(()=>state.last);
      manifests.push({...metadata,case_id:id,font_px:font,delta_g:gray,round:1,file_path:`source-images/${id}.png`});
    }
  }
  const pending=page.waitForEvent('download');
  await page.evaluate(data=>download(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),'image-manifest.json'),manifests);
  await(await pending).saveAs(`${root}/records/image-manifest.json`);
  console.log(`GENERATED: ${manifests.length} images; all layouts valid`);
}
