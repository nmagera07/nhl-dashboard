// NHL logo URLs come as the light-background version (TBL_light.svg); the
// NHL also publishes a dark-background version at the same path with
// _dark. The app is dark-themed, so prefer that -- some light versions
// (e.g. Tampa's dark blue) nearly disappear otherwise.
export function darkLogo(url) {
  return url ? url.replace(/_light\.svg$/, "_dark.svg") : url;
}
