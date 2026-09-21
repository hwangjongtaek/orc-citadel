import React from 'react';
import {createRoot} from 'react-dom/client';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {
  projectIntroduction,
  projectIntroductionHero,
  projectIntroductionNav,
  projectIntroductionStyles,
} from '@ui/project-introduction.mjs';
import {buildComponentLink} from '../../lib/component-link.js';

const h = React.createElement;
const urls = APP_URLS;

function runtimeComponents(payload) {
  if (!Array.isArray(payload?.components)) throw new Error('invalid watchtower components');
  return payload.components.map((component) => ({
    id: component.id,
    reachable: component.reachable === true,
    href: buildComponentLink(component, window.location),
  }));
}

function App() {
  const [toolState, setToolState] = React.useState({status: 'loading', components: []});

  React.useEffect(() => {
    fetch('/api/watchtower')
      .then((response) => {
        if (!response.ok) throw new Error(`watchtower status ${response.status}`);
        return response.json();
      })
      .then((payload) => setToolState({
        status: 'ready',
        components: runtimeComponents(payload),
      }))
      .catch(() => setToolState({status: 'error', components: []}));
  }, []);

  return shell({
    eyebrow: 'Project guide',
    context: 'ORC CITADEL 소개',
    urls,
    utilityNav: projectIntroductionNav({urls}),
    mastheadContent: projectIntroductionHero({urls}),
    skipTarget: 'main-content',
    slots: {
      content: h(React.Fragment, null,
        projectIntroductionStyles(),
        projectIntroduction({urls, toolState})),
    },
  });
}

createRoot(document.getElementById('root')).render(h(App));
