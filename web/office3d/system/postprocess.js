function setupPostProcessing(scene, renderer, camera, width, height) {
  const composer = new THREE.EffectComposer(renderer);

  const renderPass = new THREE.RenderPass(scene, camera);
  composer.addPass(renderPass);

  const bloomPass = new THREE.UnrealBloomPass(
    new THREE.Vector2(width || 1000, height || 580),
    0.9,
    0.6,
    0.75
  );
  composer.addPass(bloomPass);

  const smaaPass = new THREE.SMAAPass(width || 1000, height || 580);
  composer.addPass(smaaPass);

  return { composer, bloomPass };
}

function renderWithPostProcessing(composer) {
  if (!composer) return;
  composer.render();
}
