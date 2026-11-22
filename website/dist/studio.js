import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

/** A shared white studio. Scene coordinates are presentation units, not millimetres. */
export function createStudio(container,{cameraPosition=[4.5,2.8,5.2],target=[0,1.4,0],controls:interactive=false}={}) {
  const scene=new THREE.Scene();scene.background=new THREE.Color(0xffffff);
  const camera=new THREE.PerspectiveCamera(32,1,.01,100);camera.position.fromArray(cameraPosition);camera.lookAt(new THREE.Vector3().fromArray(target));
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,powerPreference:'low-power'});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.02;
  renderer.domElement.setAttribute('aria-hidden','true');container.appendChild(renderer.domElement);
  const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment(),environment=pmrem.fromScene(room,.025);
  scene.environment=environment.texture;room.dispose();pmrem.dispose();
  const key=new THREE.DirectionalLight(0xffffff,2.0);key.position.set(-3,6,4);key.castShadow=true;key.shadow.mapSize.set(2048,2048);
  Object.assign(key.shadow.camera,{left:-6,right:6,top:7,bottom:-5});key.shadow.normalBias=.015;key.shadow.bias=-.0002;scene.add(key);
  scene.add(new THREE.HemisphereLight(0xffffff,0x8793a9,.65));
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.ShadowMaterial({opacity:.11}));floor.rotation.x=-Math.PI/2;floor.position.y=-.014;floor.receiveShadow=true;scene.add(floor);
  let controls=null;
  if(interactive){controls=new OrbitControls(camera,renderer.domElement);controls.target.fromArray(target);controls.enableDamping=true;controls.enablePan=false;controls.minDistance=2;controls.maxDistance=16;controls.update();}
  const resize=()=>{const w=container.clientWidth,h=container.clientHeight;if(w&&h){camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h);}};
  new ResizeObserver(resize).observe(container);resize();
  let onScreen=true;new IntersectionObserver(([entry])=>{onScreen=entry.isIntersecting;},{rootMargin:'150px'}).observe(container);
  return {scene,camera,renderer,controls,visible:()=>onScreen&&!document.hidden,render(){controls?.update();renderer.render(scene,camera);}};
}
