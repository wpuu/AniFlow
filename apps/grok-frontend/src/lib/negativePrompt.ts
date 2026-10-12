// Agnes Video 2.5 / Flash documents one prompt, not negative_prompt.
// Keep the editable exclusions separate in storage; compose only when submitting.
export const SNOW_DIRECTOR_AVOID = [
  'photorealistic live cats or animal photography', 'real fur instead of wool fibers',
  'plastic CGI or shiny surfaces', 'flat 2D cartoon look', 'smooth fur without felt fibers',
  'extra cats or people', 'human hands', 'extra legs or paws', 'duplicated tails',
  'distorted cat face or anatomy', 'changing silver tabby markings or lab coat',
  'warped or disappearing water bowl', 'unnatural water motion',
  'text', 'subtitles', 'logos', 'watermarks', 'sudden cuts', 'camera shake',
  'frame flicker', 'unexpected scene changes',
].join(', ');

export function combineVideoPrompt(positive: string, avoid: string): string {
  const original = positive.trim();
  const exclusions = avoid.trim();
  if (!exclusions) return original;
  return `${original}\n\nAvoid these unwanted visual elements and artifacts: ${exclusions}.`;
}
