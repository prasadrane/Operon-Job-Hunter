function createLighting(scene, config) {
  // Creates all lights and adds to scene
  // Returns array of light objects

  // Ambient
  const ambient = new THREE.AmbientLight(0x1e293b, 1.2);

  // Main directional overhead
  const dir = new THREE.DirectionalLight(0xe0f2fe, 1.8);
  dir.position.set(15, 30, 20);
  dir.castShadow = true;
  dir.shadow.mapSize.width = 2048;
  dir.shadow.mapSize.height = 2048;
  dir.shadow.camera.near = 5;
  dir.shadow.camera.far = 70;
  dir.shadow.camera.left = -25;
  dir.shadow.camera.right = 25;
  dir.shadow.camera.top = 25;
  dir.shadow.camera.bottom = -25;

  // War room cyan spotlight
  const warRoomSpot = new THREE.SpotLight(0x06b6d4, 3, 25, Math.PI / 4, 0.4);
  warRoomSpot.position.set(0, 14, 0);
  warRoomSpot.target.position.set(0, 0, 0);

  // Boss suite gold spotlight
  const bossSpot = new THREE.SpotLight(0xf59e0b, 3.5, 25, Math.PI / 4, 0.3);
  bossSpot.position.set(0, 18, -16);
  bossSpot.target.position.set(0, 1.5, -16);

  // Lounge point light
  const loungePoint = new THREE.PointLight(0xfde047, 0.5, 5);
  loungePoint.position.set(-8, 2.8, 0);

  scene.add(ambient, dir, warRoomSpot, bossSpot, loungePoint);

  return [ambient, dir, warRoomSpot, bossSpot, loungePoint];
}
