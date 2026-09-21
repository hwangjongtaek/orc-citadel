import React from 'react';
import {shell, MOCKUP_URLS} from '../../../ui/shell.mjs';
import {
  projectIntroduction,
  projectIntroductionHero,
  projectIntroductionNav,
  projectIntroductionStyles,
} from '../../../ui/project-introduction.mjs';

const h = React.createElement;

export const title = '프로젝트 소개 — ORC CITADEL';

export const render = () => shell({
  eyebrow: 'Project guide',
  context: 'ORC CITADEL 소개',
  urls: MOCKUP_URLS,
  utilityNav: projectIntroductionNav({urls: MOCKUP_URLS}),
  mastheadContent: projectIntroductionHero({urls: MOCKUP_URLS}),
  skipTarget: 'main-content',
  slots: {
    content: h(React.Fragment, null,
      projectIntroductionStyles(),
      projectIntroduction({urls: MOCKUP_URLS})),
  },
});
