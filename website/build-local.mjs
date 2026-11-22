import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { Script } from 'node:vm';
import { fileURLToPath } from 'node:url';

const root=path.dirname(fileURLToPath(import.meta.url));
const dist=path.join(root,'dist');
const output=path.resolve(root,process.argv[2]??'standalone/OpenTDCR.html');
const read=(name)=>readFile(path.join(dist,name),'utf8');
const data=async(name,mime)=>`data:${mime};base64,${(await readFile(path.join(dist,name))).toString('base64')}`;
const escapeScript=(s)=>s.replace(/<\/script/gi,'<\\/script');
const bundle=await build({entryPoints:[path.join(dist,'app.js')],bundle:true,format:'iife',target:'es2020',minify:true,legalComments:'inline',write:false});
let css=await read('style.css');
css=css.replace(/@import\s+url\([^;]+\);/g,'');
let fontCSS=await read('fonts.css');
for(const match of [...fontCSS.matchAll(/url\(['"]?([^)'"\s]+)['"]?\)/g)]){
  fontCSS=fontCSS.replace(match[0],`url("${await data(match[1],'font/woff2')}")`);
}
let html=await read('index.html');
html=html.replace(/<script type="importmap">[\s\S]*?<\/script>/,'');
html=html.replace(/<link rel="stylesheet" href="fonts.css">/,'');
html=html.replace('<link rel="stylesheet" href="style.css">',()=>`<style>${fontCSS}\n${css}\n</style>`);
html=html.replace('href="assets/icon.svg"',`href="${await data('assets/icon.svg','image/svg+xml')}"`);
for(const match of [...html.matchAll(/<img\b[^>]*?\bsrc="(assets\/[^" ]+)"/g)]){
  const mime=match[1].endsWith('.svg')?'image/svg+xml':match[1].endsWith('.jpg')?'image/jpeg':'image/png';
  html=html.replaceAll(`src="${match[1]}"`,`src="${await data(match[1],mime)}"`);
}
const model=(await readFile(path.join(dist,'assets/cad/assembly-optimized.glb'))).toString('base64');
const notices={
  'Three.js':await read('vendor/three/LICENSE'),
  'DM Sans':await read('assets/fonts/DM-Sans-OFL.txt'),
  'Manrope':await read('assets/fonts/Manrope-OFL.txt'),
  'Meshopt decoder':(await read('vendor/three/addons/libs/meshopt_decoder.module.js')).split('\n').slice(0,2).join('\n')+'\n\n'+(await read('vendor/three/LICENSE')).split('Permission is hereby granted')[1].replace(/^/,'Permission is hereby granted'),
  'Identity':JSON.parse(await read('assets/identity/sources.json')),
  'Hardware':'See hardware/LICENSING.md in the source repository. No new hardware redistribution license is asserted.'
};
const documentUI=`
<script type="application/json" id="opentdcr-notices">${JSON.stringify(notices).replaceAll('<','\\u003c')}</script>`;
html=html.replace('<script type="module" src="app.js"></script>',()=>`<script type="application/octet-stream" id="opentdcr-assembly">${model}</script>\n<script>${escapeScript(bundle.outputFiles[0].text)}</script>\n${documentUI}`);
const executableScripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if(executableScripts.length!==1)throw new Error('Standalone script structure invalid');
for(const [index,match] of executableScripts.entries())new Script(match[1],{filename:`standalone-script-${index}.js`});
await mkdir(path.dirname(output),{recursive:true});await writeFile(output,html);
console.log(`Standalone HTML: ${output}\n${Buffer.byteLength(html).toLocaleString()} bytes; scripts, fonts and CAD embedded; code and documentation are linked on GitHub.`);
