import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
let assemblyPromise;
/** Share decoding, while each view receives independent object transforms/materials. */
export async function loadAssembly(){
  if(!assemblyPromise){
    const loader=new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
    assemblyPromise=new Promise((resolve,reject)=>{
      const embedded=document.getElementById('opentdcr-assembly');
      if(embedded){const bytes=Uint8Array.from(atob(embedded.textContent.trim()),c=>c.charCodeAt(0));loader.parse(bytes.buffer,'',resolve,reject);}
      else loader.load('./assets/cad/assembly-optimized.glb',resolve,undefined,reject);
    });
  }
  const {scene}=await assemblyPromise;const model=scene.clone(true);
  model.traverse(node=>{if(node.isMesh){node.castShadow=true;node.receiveShadow=true;if(Array.isArray(node.material))node.material=node.material.map(m=>m.clone());else if(node.material)node.material=node.material.clone();}});
  return model;
}
