import {writeFile} from 'node:fs/promises';
const names = ['google','microsoft','ibm','airbnb','spotify','github','adobe','paypal','slack','zoom','dropbox','atlassian','docker','firefox','opera','safari','chrome','mailchimp','wordpress','apple'];
const base = 'https://raw.githubusercontent.com/gilbarbara/logos/main/logos/';
const results = await Promise.all(names.map(async name => {
  const url = `${base}${name}.svg`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${name}: ${response.status}`);
  const svg = await response.text();
  if (!svg.includes('<svg')) throw new Error(`${name}: not SVG`);
  await writeFile(new URL(`assets/${name}.svg`, import.meta.url), svg);
  return {name, url};
}));
await writeFile(new URL('assets/sources.json', import.meta.url), JSON.stringify(results, null, 2));
console.log(`Downloaded ${results.length} SVG logos.`);
