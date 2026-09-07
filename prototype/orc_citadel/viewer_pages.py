"""뷰어 페이지 HTML 템플릿 (stdlib, read-only).

`viewer.py` 의 dispatch 는 라우트당 페이지 문자열을 이 모듈에서 가져와 서빙한다.
JS 는 각 페이지가 `viewer.py` 의 `/api/*` JSON 엔드포인트를 fetch 해 클라이언트 렌더
(기존 `_PAGE` 패턴). 공유 CSS·공유 내비(경량 기능 링크)를 여기서 집중한다.

장식·애니메이션·일러스트는 범위 밖 (handoff-viewer-pages.md §2-4). read-only·결정적.
"""
import html

# 공유 스타일 — DESIGN.md 토큰 + 목업 공유 셸 (docs/mockups/*.html 인라인 셸 재현).
# 외부 폰트(Cinzel/Space Grotesk/Inter/JetBrains)는 오프라인 stdlib 뷰어라
# --font-* 의 로컬 fallback 스택으로 대체 (목업 자체가 fallback 병기).
CSS = """
<style>
 /* 값의 정본은 design-system/theme-citadel (DESIGN.md 발행본)이다.
    여기서는 뷰어가 오래 써 온 의미론적 이름을 Astryx 토큰에 얹는 얇은 별칭만 둔다.
    폴백 hex 는 자산 서빙이 안 되는 환경(테마 CSS 미로드)에서도 화면이 서게 한다. */
 :root{
   --citadel-void:var(--color-background-body,#07111C);
   --citadel-night:var(--color-background-surface,#0D1B2A);
   --surface:var(--color-background-card,#111820);
   --surface-variant:var(--color-background-muted,#26313A);
   --on-surface:var(--color-text-primary,#D6CCB8);
   --on-surface-muted:var(--color-text-secondary,#59636A);
   --parchment:var(--astryx-theme-citadel-parchment,#C8B58E);
   --primary:var(--color-accent,#45E06F);
   --secondary:var(--astryx-theme-citadel-seer-green,#20B85A);
   --ember:var(--astryx-theme-citadel-ember,#E97824);
   --signal-amber:var(--astryx-theme-citadel-signal-amber,#FFB13B);
   --crimson:var(--astryx-theme-citadel-crimson,#7B2833);
   --error:var(--color-error,#E05252);
   --uncertain:var(--astryx-theme-citadel-uncertain,#A78BFA);
   --superseded:var(--astryx-theme-citadel-superseded,#59636A);
   --font-display:var(--astryx-theme-citadel-font-display,"Cinzel",Georgia,serif);
   --font-head:var(--font-family-heading,"Space Grotesk",system-ui,sans-serif);
   --font-body:var(--font-family-body,"Inter",system-ui,sans-serif);
   --font-data:var(--font-family-code,"JetBrains Mono",ui-monospace,monospace);
   --r-sm:var(--radius-inner,4px); --r-md:var(--radius-element,8px);
   --r-lg:var(--radius-container,12px); --r-full:var(--radius-full,9999px);
   --sp-xs:4px; --sp-sm:8px; --sp-md:16px; --sp-lg:24px; --sp-xl:32px;
 }
 *{box-sizing:border-box;margin:0;padding:0}
 body{font-family:var(--font-body);background:var(--citadel-void);color:var(--on-surface);font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased}
 .app{min-height:100vh;background:var(--citadel-night)}
 main{max-width:1200px;margin:0 auto;padding:var(--sp-md) var(--sp-lg) var(--sp-xl)}
 .mono{font-family:var(--font-data)}
 a{color:var(--secondary);text-decoration:none} a:hover{color:var(--primary);text-decoration:underline}
 ::selection{background:rgba(69,224,111,.25)}
 h1{font-size:20px;margin:0 0 4px;font-family:var(--font-head)}
 .sub{color:var(--on-surface-muted);margin-bottom:20px}
 header{display:flex;align-items:center;gap:var(--sp-lg);padding:10px var(--sp-lg);background:var(--surface);border-bottom:1px solid var(--surface-variant)}
 .wordmark{font-family:var(--font-display);font-weight:700;font-size:18px;letter-spacing:.14em;color:var(--on-surface);display:flex;align-items:center;gap:10px;white-space:nowrap}
 .crest{width:22px;height:22px;flex:none;display:grid;place-items:center;color:var(--primary)}
 .space{display:flex;flex-direction:column;min-width:0;padding-left:var(--sp-lg);border-left:1px solid var(--surface-variant)}
 .space .eyebrow{font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--on-surface-muted)}
 .space .title{font-family:var(--font-head);font-size:15px;font-weight:600;color:var(--on-surface);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .grow{flex:1 1 auto}
 .search{display:flex;align-items:center;gap:8px;background:var(--surface-variant);border-radius:var(--r-md);padding:8px 12px;width:300px;max-width:32vw;color:var(--on-surface-muted)}
 .search svg{flex:none}
 .search input{background:none;border:none;outline:none;color:var(--on-surface);font-family:var(--font-body);font-size:13px;width:100%}
 .search input::placeholder{color:var(--on-surface-muted)}
 .spire{position:relative;display:flex;align-items:center;gap:8px;font-family:var(--font-head);font-size:12px;font-weight:600;color:var(--signal-amber);background:rgba(255,177,59,.08);border:1px solid rgba(255,177,59,.3);padding:8px 12px;border-radius:var(--r-md);cursor:pointer;white-space:nowrap}
 .spire .dot{width:7px;height:7px;border-radius:var(--r-full);background:var(--signal-amber);box-shadow:0 0 8px 1px var(--signal-amber)}
 /* 크기는 shell() 이 인라인으로 준다 (공간별 히어로·상한). 스크림이 아래에서
    위로 걷혀 글자만 덮고 그림 본체는 살린다.
    폭은 본문(main)과 맞춘다 — 전폭이면 본문과 어긋나고, 넓을수록 8:3 상한에
    걸려 세로가 더 잘린다(2560px 전폭 37% vs 1200px 80%). */
 .masthead{position:relative;overflow:hidden;flex:none;
   max-width:1200px;width:calc(100% - var(--sp-lg) * 2);margin:var(--sp-md) auto 0;
   border:1px solid var(--surface-variant);border-radius:var(--r-lg);
   display:flex;align-items:flex-end;padding:0 var(--sp-lg) 20px}
 .masthead h1{font-family:var(--font-head);font-size:22px;font-weight:600;color:var(--on-surface);letter-spacing:-.01em;text-shadow:0 2px 14px rgba(7,17,28,.9)}
 .masthead p{font-family:var(--font-head);font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--parchment);margin-top:5px;text-shadow:0 2px 14px rgba(7,17,28,.9)}
 .spaces{display:flex;flex-wrap:wrap;gap:2px;margin-bottom:var(--sp-lg)}
 .spaces a{padding:6px 12px;border-radius:var(--r-md);font-family:var(--font-head);font-size:12px;font-weight:600;color:var(--on-surface-muted)}
 .spaces a:hover{color:var(--on-surface);background:var(--surface-variant)}
 .spaces a.active{color:var(--primary);background:rgba(69,224,111,.08)}
 .panel,.card{background:var(--surface);border:1px solid var(--surface-variant);border-radius:var(--r-lg);overflow:hidden}
 .card{margin-bottom:var(--sp-md)}
 .card>.body,.panel-body{padding:var(--sp-md)}
 .panel-head{display:flex;align-items:center;justify-content:space-between;padding:12px var(--sp-md);border-bottom:1px solid var(--surface-variant)}
 .panel-head h2{font-family:var(--font-head);font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface)}
 .panel-head .sub{font-family:var(--font-head);font-size:10px;letter-spacing:.08em;color:var(--on-surface-muted);text-transform:uppercase}
 h2.h{font-family:var(--font-head);font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface);margin:var(--sp-md) 0 10px;display:flex;align-items:center;gap:8px}
 h2.h::after{content:"";flex:1;height:1px;background:var(--surface-variant)}
 table{border-collapse:collapse;width:100%;font-size:13px}
 th{font-family:var(--font-head);font-size:9.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface-muted);text-align:left;padding:8px 10px;border-bottom:1px solid var(--surface-variant);white-space:nowrap}
 td{padding:11px 10px;border-bottom:1px solid rgba(38,49,58,.5);vertical-align:middle}
 tr:last-child td{border-bottom:none}
 tbody tr:hover td{background:rgba(38,49,58,.28)}
 td.num,th.num{text-align:right;font-family:var(--font-data)}
 .empty-art{display:block;margin:0 auto 12px;width:132px;height:132px;image-rendering:pixelated;opacity:.9}
 .badge{display:inline-block;font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:var(--r-sm);background:var(--surface-variant);color:var(--on-surface)}
 .badge.good{background:rgba(69,224,111,.14);color:var(--primary)}
 .badge.warn{background:rgba(255,177,59,.14);color:var(--signal-amber)}
 .badge.err{background:rgba(224,82,82,.14);color:var(--error)}
 .badge.uncert{background:rgba(167,139,250,.14);color:var(--uncertain)}
 .pill{display:inline-block;font-family:var(--font-head);font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;padding:3px 10px;border-radius:var(--r-md)}
 .pill.hi{background:rgba(69,224,111,.14);color:var(--primary)}
 .pill.normal{background:var(--surface-variant);color:var(--on-surface)}
 .pill.med{background:rgba(255,177,59,.14);color:var(--signal-amber)}
 .pill.lo{background:rgba(224,82,82,.14);color:var(--error)}
 .pill.contradicted{background:rgba(123,40,51,.55);color:var(--error)}
 .chip{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-head);font-size:11px;font-weight:500;padding:5px 10px;border-radius:var(--r-full);border:1px solid var(--surface-variant);color:var(--on-surface);margin:0 6px 6px 0}
 .chip .sw{width:8px;height:8px;border-radius:var(--r-full);display:inline-block}
 .sec-label{font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--on-surface-muted);display:flex;align-items:center;gap:8px;margin:var(--sp-md) 0 10px}
 .sec-label::after{content:"";flex:1;height:1px;background:var(--surface-variant)}
 .span{font-family:var(--font-data);font-size:11px;color:var(--parchment);background:var(--surface-variant);padding:8px 10px;border-radius:var(--r-sm)}
 .trail{display:flex;gap:6px;flex-wrap:wrap;font-family:var(--font-data);font-size:10px;color:var(--on-surface-muted)}
 .conf{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--surface-variant);border:1px solid var(--surface-variant);border-radius:var(--r-md);overflow:hidden}
 .conf .cell{background:var(--surface);padding:10px 12px}
 .conf .num{font-family:var(--font-head);font-size:20px;font-weight:600;color:var(--on-surface)}
 .conf .num.good{color:var(--primary)}
 .conf .cap{font-family:var(--font-head);font-size:9.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--on-surface-muted)}
 .btn{font-family:var(--font-head);font-size:11px;font-weight:600;padding:6px 12px;border-radius:var(--r-md);border:1px solid var(--surface-variant);color:var(--on-surface);background:none;cursor:pointer}
 .btn.primary{border-color:var(--primary);color:var(--primary);background:rgba(69,224,111,.06)}
 .btn.run{border:none;color:var(--citadel-void);background:var(--primary);box-shadow:0 0 0 1px rgba(69,224,111,.4),0 6px 18px -6px rgba(69,224,111,.5)}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--sp-md);margin-bottom:var(--sp-md)}
 .bar{background:var(--surface-variant);border-radius:6px;height:10px;width:140px;display:inline-block;vertical-align:middle;margin-right:8px;overflow:hidden}
 .bar>i{display:block;height:100%;background:var(--primary)}
 .dim{font-size:12px;color:var(--on-surface-muted)} .muted{color:var(--on-surface-muted)}
 .err{color:var(--error)} .na{color:var(--signal-amber)}
 code,pre{font-family:var(--font-data);font-size:12px;color:var(--parchment)}
 ::-webkit-scrollbar{width:8px;height:8px} ::-webkit-scrollbar-thumb{background:var(--surface-variant);border-radius:var(--r-full)}
 .wt-layout{display:grid;grid-template-columns:250px 1fr 300px;border:1px solid var(--surface-variant);border-radius:var(--r-lg);overflow:hidden;min-height:520px;margin-bottom:var(--sp-md)}
 .wt-layout>.panel{border-radius:0;margin:0;border:none;border-right:1px solid var(--surface-variant);display:flex;flex-direction:column;min-height:0}
 .wt-layout>.panel:last-child{border-right:none}
 .wt-layout .panel-body{overflow-y:auto;flex:1}
 .subq{padding:10px 12px;border-radius:var(--r-md);border:1px solid var(--surface-variant);margin-bottom:10px;cursor:pointer}
 .subq:hover{border-color:var(--on-surface-muted)}
 .subq.active{border-color:var(--primary);background:rgba(69,224,111,.06)}
 .subq .q{font-size:13px;color:var(--on-surface);margin-bottom:8px}
 .subq .meta{display:flex;align-items:center;gap:10px;font-size:11px;color:var(--on-surface-muted)}
 .cov{flex:1;height:4px;border-radius:var(--r-full);background:var(--surface-variant);overflow:hidden}
 .cov>i{display:block;height:100%;background:var(--primary);border-radius:var(--r-full)}
 .filters-label{font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--on-surface-muted);margin:var(--sp-lg) 0 10px}
 .wt-head{display:flex;align-items:center;justify-content:space-between;padding:12px var(--sp-md);border-bottom:1px solid var(--surface-variant);gap:var(--sp-md)}
 .wt-head .name{display:flex;align-items:baseline;gap:10px}
 .wt-head .name h2{font-family:var(--font-head);font-size:15px;font-weight:600;color:var(--on-surface);letter-spacing:0;text-transform:none}
 .wt-head .name .fn{font-family:var(--font-head);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface-muted)}
 .legend{display:flex;gap:var(--sp-md);flex-wrap:wrap}
 .lg{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--on-surface-muted);font-family:var(--font-head)}
 .wt-canvas{position:relative;flex:1;min-height:280px;background:radial-gradient(800px 400px at 50% 42%,rgba(38,49,58,.5),transparent 70%),var(--citadel-night)}
 .wt-graph{width:100%;height:280px;display:block}
 .node-label{font-family:var(--font-head);font-weight:600;font-size:11px;fill:var(--on-surface)}
 .node-type{font-family:var(--font-head);font-weight:600;font-size:8px;letter-spacing:.1em;text-transform:uppercase;fill:var(--on-surface-muted)}
 .node-sub{font-family:var(--font-body);font-size:10px;fill:var(--on-surface-muted)}
 .edge-label{font-family:var(--font-head);font-size:9px;letter-spacing:.06em;text-transform:uppercase;fill:var(--on-surface-muted)}
 .timebar{position:absolute;left:var(--sp-md);right:var(--sp-md);bottom:var(--sp-md);display:flex;align-items:center;gap:var(--sp-md);background:rgba(7,17,28,.72);border:1px solid var(--surface-variant);border-radius:var(--r-md);padding:8px 12px}
 .timebar .lbl{font-family:var(--font-head);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface-muted);white-space:nowrap}
 .timebar input{flex:1}
 .timebar .val{font-family:var(--font-data);font-size:12px;color:var(--on-surface);white-space:nowrap}
 .claim-card{border:1px solid var(--primary);background:rgba(69,224,111,.05);border-radius:var(--r-md);padding:12px;margin-bottom:var(--sp-md)}
 .claim-card .text{font-size:14px;line-height:1.55}
 .claim-card .id{font-size:10.5px;color:var(--on-surface-muted);margin-top:8px}
 .ev{border:1px solid var(--surface-variant);border-radius:var(--r-md);padding:10px 12px;margin-bottom:10px;border-left-width:3px}
 .ev.support{border-left-color:var(--primary)}
 .ev.contra{border-left-color:var(--error)}
 .ev .top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
 .ev .rel{font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase}
 .ev.support .rel{color:var(--primary)}
 .ev .src{font-family:var(--font-head);font-size:10px;color:var(--on-surface-muted)}
 .indep{font-size:11px;color:var(--on-surface-muted);background:rgba(255,177,59,.06);border:1px solid rgba(255,177,59,.25);border-radius:var(--r-md);padding:8px 12px;margin-bottom:var(--sp-md)}
 .indep b{color:var(--signal-amber);font-family:var(--font-head)}
 .seer{border:1px dashed var(--secondary);border-radius:var(--r-md);padding:10px 12px;background:rgba(32,184,90,.05)}
 .seer .hd{font-family:var(--font-head);font-size:11px;font-weight:600;color:var(--secondary);margin-bottom:6px}
 .seer .body{font-size:12px;color:var(--on-surface-muted)}
 .wt-chronicle{background:var(--surface);border:1px solid var(--surface-variant);border-radius:var(--r-lg);padding:10px var(--sp-lg);display:flex;align-items:center;gap:var(--sp-lg);margin-bottom:var(--sp-md)}
 .wt-chronicle .lead{display:flex;flex-direction:column;white-space:nowrap}
 .wt-chronicle .lead .t{font-family:var(--font-head);font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase}
 .wt-chronicle .lead .s{font-family:var(--font-head);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--on-surface-muted)}
 .rail{position:relative;flex:1;height:46px}
 .rail .line{position:absolute;left:0;right:0;top:50%;height:1px;background:var(--surface-variant)}
 .event{position:absolute;top:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;font-family:var(--font-data);font-size:9.5px;color:var(--on-surface-muted);white-space:nowrap}
 .event .pin{width:9px;height:9px;border-radius:var(--r-full);background:var(--primary);border:2px solid var(--citadel-night)}
 .event .lab{position:absolute;top:-18px}
 .event .date{position:absolute;top:14px}
 .empty-state{padding:var(--sp-lg);text-align:center;color:var(--on-surface-muted)}
 .empty-state .trig{font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--signal-amber);margin-bottom:8px}
 .gn{cursor:pointer}
 .wt-list{padding:8px var(--sp-md) 12px;font-size:11px;color:var(--on-surface-muted);border-top:1px solid var(--surface-variant);max-height:120px;overflow-y:auto}
 @media (max-width:1100px){.wt-layout{grid-template-columns:220px 1fr 260px}}
 .wit-layout{display:grid;grid-template-columns:300px 1fr 340px;border:1px solid var(--surface-variant);border-radius:var(--r-lg);overflow:hidden;min-height:540px;margin-bottom:var(--sp-md)}
 .wit-layout>.panel{border-radius:0;margin:0;border:none;border-right:1px solid var(--surface-variant);display:flex;flex-direction:column;min-height:0}
 .wit-layout>.panel:last-child{border-right:none}
 .wit-layout .panel-body{overflow-y:auto;flex:1}
 .claim-row{padding:10px 12px;border-radius:var(--r-md);border:1px solid var(--surface-variant);margin-bottom:10px;cursor:pointer}
 .claim-row:hover{border-color:var(--on-surface-muted)}
 .claim-row.active{border-color:var(--primary);background:rgba(69,224,111,.06)}
 .claim-row .q{font-size:13px;color:var(--on-surface);margin-bottom:6px}
 .claim-row .cid{font-family:var(--font-data);font-size:10px;color:var(--on-surface-muted)}
 .claim-row .foot{display:flex;align-items:center;justify-content:space-between;margin-top:6px}
 .cmini b{font-family:var(--font-head);font-size:13px;color:var(--primary)}
 .mid-body{padding:var(--sp-md);overflow-y:auto}
 .prov-step{display:flex;gap:10px;align-items:flex-start}
 .prov-rail{display:flex;flex-direction:column;align-items:center;min-width:14px}
 .prov-rail .node{width:10px;height:10px;border-radius:var(--r-full);background:var(--primary);margin-top:4px}
 .prov-rail .link{width:2px;flex:1;min-height:24px;background:var(--surface-variant)}
 .prov-main{flex:1;padding-bottom:14px}
 .prov-main .lbl{font-family:var(--font-head);font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--on-surface-muted)}
 .prov-main .val{font-size:12.5px;color:var(--on-surface);margin:3px 0}
 .prov-main .fields{display:flex;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--on-surface-muted)}
 .doc-panel{background:var(--citadel-night)}
 .doc-toolbar{display:flex;align-items:center;gap:10px;padding:8px var(--sp-md);border-bottom:1px solid var(--surface-variant);font-size:11px}
 .doc-scroll{padding:var(--sp-md);overflow-y:auto;flex:1}
 .parch{background:#0f1720;border:1px solid var(--surface-variant);border-radius:var(--r-md);padding:16px;line-height:1.7;font-size:12.5px;color:var(--on-surface)}
 .parch .doc-title{font-family:var(--font-head);font-weight:600;margin-bottom:10px;color:var(--parchment)}
 .parch .off{font-family:var(--font-data);font-size:9px;color:var(--on-surface-muted)}
 .parch .hl{border-radius:3px;padding:1px 3px;position:relative}
 .parch .hl.support{background:rgba(69,224,111,.16);color:#d6ffdd}
 .parch .hl.contra{background:rgba(224,82,82,.16)}
 .roundtrip{background:var(--surface);border:1px solid var(--surface-variant);border-radius:var(--r-md);padding:10px var(--sp-md);display:flex;align-items:center;gap:14px;font-size:12px}
 .roundtrip .lead{font-family:var(--font-head);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface-muted)}
 .roundtrip .hop{display:inline-flex;align-items:center;gap:6px}
 .roundtrip .n{width:18px;height:18px;border-radius:var(--r-full);background:var(--surface-variant);display:inline-grid;place-items:center;font-family:var(--font-data);font-size:11px}
 .roundtrip .goal{margin-left:auto;color:var(--on-surface-muted);font-size:11px}
 .cncl-grid{display:grid;grid-template-columns:280px 1fr 320px;border:1px solid var(--surface-variant);border-radius:var(--r-lg);overflow:hidden;min-height:520px;margin-bottom:var(--sp-md)}
 .cncl-grid>.panel{border-radius:0;margin:0;border:none;border-right:1px solid var(--surface-variant);display:flex;flex-direction:column;min-height:0}
 .cncl-grid>.panel:last-child{border-right:none}
 .cncl-grid .panel-body{overflow-y:auto;flex:1}
 .formula{font-family:var(--font-data);font-size:11px;background:var(--surface-variant);border-radius:var(--r-sm);padding:8px 10px;margin-bottom:12px}
 .cond{margin-bottom:10px}
 .cond .ct{display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:5px}
 .cond .ck{font-family:var(--font-head);font-size:9px;font-weight:700;letter-spacing:.08em;color:var(--on-surface-muted);width:14px}
 .cond .cn{color:var(--on-surface)}
 .cond .cv{margin-left:auto;font-family:var(--font-data);font-size:11px;color:var(--on-surface-muted)}
 .cond .bar{height:5px;border-radius:var(--r-full);background:var(--surface-variant);overflow:hidden}
 .cond .bar>i{display:block;height:100%;border-radius:var(--r-full)}
 .cost-grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--surface-variant);border:1px solid var(--surface-variant);border-radius:var(--r-md);overflow:hidden;margin-bottom:12px}
 .cost-grid .cell{background:var(--surface);padding:9px 11px}
 .cost-grid .num{font-family:var(--font-head);font-size:16px;font-weight:600;color:var(--on-surface)}
 .cost-grid .cap{font-family:var(--font-head);font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:var(--on-surface-muted);margin-top:3px}
 .arow{display:flex;align-items:center;gap:10px;padding:7px 0}
 .arow+.arow{border-top:1px solid var(--surface-variant)}
 .arow .al{font-size:12px;color:var(--on-surface);line-height:1.4}
 .arow .as{display:block;font-size:10.5px;color:var(--on-surface-muted)}
 @media (max-width:1100px){.wit-layout{grid-template-columns:240px 1fr 280px}.cncl-grid{grid-template-columns:1fr}}
</style>
"""


def nav(cur: str) -> str:
    """공간 전환 탭 (목업 .spaces 셸). `cur` 가 현재 페이지면 active."""
    links = [
        ("/", "Citadel Gate"),
        ("/table", "War Table"),
        ("/witnesses", "Hall of Witnesses"),
        ("/council", "Council Chamber"),
        ("/watchtower", "Watchtower"),
        ("/archive", "Grand Archive"),
        ("/chronicle", "Chronicle Vault"),
        ("/spire", "Signal Spire"),
    ]
    tabs = "".join(
        f'<a class="{"active" if (r == cur) else ""}" href="{r}">{html.escape(t)}</a>'
        for r, t in links
    )
    return f'<nav class="spaces">{tabs}</nav>'


def _crest() -> str:
    """워드마크 쉴드(SVG) — 목업 .crest 재현."""
    return ('<span class="crest" aria-hidden="true">'
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none">'
            '<path d="M12 2 L20 6 V13 C20 18 12 22 12 22 C12 22 4 18 4 13 V6 Z" '
            'stroke="currentColor" stroke-width="1.6" fill="rgba(69,224,111,.07)"/>'
            '<path d="M9 9 Q12 12 15 9 M12 11 V15" stroke="currentColor" stroke-width="1.6" '
            'stroke-linecap="round"/><circle cx="12" cy="8" r="1.3" fill="currentColor"/>'
            '</svg></span>')


def _search_icon() -> str:
    return ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none">'
            '<circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2"/>'
            '<path d="M20 20 L16.5 16.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            '</svg>')


# 공간별 (라우트) 브레이드크럼 — (eyebrow EN·function, title KO).
# 공간별 빈 상태 일러스트 (docs/mockups/empty-states.html 패턴).
# Gate·Council 은 대응 아트가 없다 — 없으면 텍스트만 (정직 갭).
_EMPTY_ART = {
    "/table": "empty-wartable.png",
    "/witnesses": "empty-witnesses.png",
    "/watchtower": "empty-watchtower.png",
    "/archive": "empty-archive.png",
    "/chronicle": "empty-chronicle.png",
    "/spire": "empty-spire.png",
}

_SPACE_META = {
    "/":         ("Citadel Gate · Home", "본부 · Home", "gate-hero.png", 360),
    "/table":    ("War Table · Graph", "조사 · 그래프", "war-table-hero.png", 300),
    "/witnesses": ("Hall of Witnesses · Evidence", "증거 검사",
                   "hall-of-witnesses-hero.png", 300),
    "/council":  ("Council Chamber · Investigation", "조사 보고서",
                  "council-chamber-hero.png", 300),
    "/watchtower": ("Watchtower · Ingestion", "수집 관제", "watchtower-hero.png", 360),
    "/archive":  ("Grand Archive · Documents", "문서 탐색", "grand-archive-hero.png", 300),
    "/chronicle": ("Chronicle Vault · History", "시간 탐색",
                   "chronicle-vault-hero.png", 300),
    "/spire":    ("Signal Spire · Alerts", "알림 센터", "signal-spire-hero.png", 300),
}


def shell(route: str, body: str, title: str) -> str:
    """목업 공유 셸로 페이지를 감싼 전체 HTML.

    header(워드마크+브레이드크럼+검색+Signal Spire 칩)·masthead 밴드·공간 탭을
    포함하고, `body`(페이지 본문+JS)를 main 에 넣는다.

    색·형태·폰트의 정본은 `design-system/theme-citadel` 이며 `/assets/*` 로 서빙된다
    (viewer_static.py). 스코프 루트를 `<html>` 에 두는 이유는 astryx 기본 토큰이
    `:root` 에 `light-dark()` 로 깔려 있어서다 — `<body>` 를 루트로 잡으면 `<html>`
    이 라이트 팔레트를 써서 본문 아래가 흰색으로 남는다(다크 모드에선 안 드러남).
    """
    eyebrow, app_title, hero, cap = _SPACE_META.get(route, _SPACE_META["/"])
    # 히어로는 전부 1920×720 (8:3). 고정 높이 밴드에 cover 로 넣으면 세로 23% 만
    # 보여 장면이 안 읽힌다 — 8:3 을 지키되 상한으로 본문 공간을 지킨다.
    # 상한이 없으면 2560px 뷰포트에서 960px 를 먹는다.
    mast_style = (
        f"aspect-ratio:8/3;max-height:{cap}px;min-height:150px;"
        "background:"
        "linear-gradient(0deg,rgba(7,17,28,.94) 0%,rgba(7,17,28,.55) 26%,"
        "rgba(7,17,28,.12) 55%,rgba(7,17,28,0) 80%),"
        f"url('/assets/img/{hero}') center center / cover no-repeat,"
        "var(--citadel-night)")
    return (
        # 빈 상태 아트는 라우트에서 정해진다 — `window.empty()` 가 집어간다.
        # script 태그가 아니라 data 속성인 이유: `_inject` 가 페이지당 <script> 를
        # 정확히 하나로 유지하는 것을 병합 앵커 불변식으로 삼는다.
        f'<!doctype html><html lang="ko" data-astryx-theme="citadel"'
        f' data-empty-art="{_EMPTY_ART.get(route, "")}">'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        # 폰트 → 테마 → 뷰어 CSS 순. 뒤엣것이 앞을 덮는다.
        '<link rel="stylesheet" href="/assets/fonts/fonts.css">'
        '<link rel="stylesheet" href="/assets/theme-citadel.css">' + CSS +
        '<body><div class="app">'
        "<header>"
        f'<a class="wordmark" href="/">{_crest()}ORC&nbsp;CITADEL</a>'
        f'<div class="space"><span class="eyebrow">{html.escape(eyebrow)}</span>'
        f'<span class="title">{html.escape(app_title)}</span></div>'
        '<div class="grow"></div>'
        f'<label class="search">{_search_icon()}'
        '<input placeholder="entity · claim · source 검색" /></label>'
        '<a class="spire" href="/spire" title="Signal Spire · 결론·confidence 변화 알림">'
        '<span class="dot"></span> Signal Spire · 0</a>'
        "</header>"
        f'<div class="masthead" style="{mast_style}"><div class="mh-txt">'
        f"<h1>{html.escape(app_title)}</h1><p>{html.escape(eyebrow)}</p></div></div>"
        "<main>" + nav(route) + body + "</main>"
        "</div></body></html>"
    )


def _esc(v):
    return html.escape(str(v))


def _esc(v):
    return html.escape(str(v))


# --- War Table — 조사 그래프 3+1 (`/table`). ---
PAGE_TABLE = shell(
    "/table",
    """<div class="wt-layout">
  <section class="panel" id="campaign-map">
    <div class="panel-head"><h2>Campaign Map</h2><span class="sub" id="map-sub">Subjects · 0</span></div>
    <div class="panel-body">
      <div id="subq-list"></div>
      <div id="pred-list"></div>
      <div class="filters-label">Entities · Filters</div>
      <div id="type-chips"></div>
    </div>
  </section>
  <section class="panel" id="war-canvas">
    <div class="wt-head">
      <div class="name"><h2>War Table</h2><span class="fn">· Temporal Evidence Graph</span></div>
      <div class="legend" aria-label="관계 유형 범례">
        <span class="lg"><svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="#45E06F" stroke-width="2"/></svg>supports</span>
        <span class="lg"><svg width="26" height="8"><line x1="0" y1="2.5" x2="26" y2="2.5" stroke="#E05252" stroke-width="1.5"/><line x1="0" y1="5.5" x2="26" y2="5.5" stroke="#E05252" stroke-width="1.5"/></svg>contradicts</span>
        <span class="lg"><svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="#FFB13B" stroke-width="2" stroke-dasharray="5 3"/></svg>qualifies</span>
        <span class="lg"><svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="#A78BFA" stroke-width="2" stroke-dasharray="2 3"/></svg>uncertain</span>
        <span class="lg"><svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="#59636A" stroke-width="2" stroke-dasharray="1 3"/></svg>superseded</span>
      </div>
    </div>
    <div class="wt-canvas">
      <svg class="wt-graph" id="wt-svg" viewBox="0 0 900 280" preserveAspectRatio="xMidYMid meet"></svg>
      <div class="timebar">
        <span class="lbl">Valid time</span>
        <input id="time-slider" type="range" min="0" max="0" value="0">
        <span class="val" id="time-val">TX · now</span>
      </div>
    </div>
    <div class="wt-list" id="wt-list"></div>
  </section>
  <section class="panel" id="inspector">
    <div class="panel-head"><h2>Evidence Inspector</h2><span class="sub">Hall of Witnesses</span></div>
    <div class="panel-body" id="inspector-body"></div>
  </section>
</div>
<div class="wt-chronicle" id="chronicle-rail">
  <div class="lead"><span class="t">Chronicle</span><span class="s">Bitemporal History</span></div>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}
function pill(s){return s==='high_confidence'?'<span class="pill hi">high</span>':s==='contradicted'
  ?'<span class="pill contradicted">contradicted</span>':s==='low_evidence'?'<span class="pill lo">low evidence</span>'
  :'<span class="pill normal">normal</span>';}
function empty(trig,msg){return '<div class="empty-state"><div class="trig">'+esc(trig)+'</div><p>'+esc(msg)+'</p></div>';}

let seed={subjects:[],entity_types:[],notes:{}};
let filter='';
let current=null;
let sg=null;
let claimIds=new Set();
let focus=null;
let ticks=[];

function renderCampaign(){
  const q=filter.toLowerCase();
  const rows=(seed.subjects||[]).filter(s=>!q||String(s.subject_id).toLowerCase().includes(q));
  $('#subq-list').innerHTML=rows.map(s=>{
    const cov=Math.round((s.coverage||0)*100);
    return '<div class="subq'+(s.subject_id===current?' active':'')+'" data-subj="'+esc(s.subject_id)+'">'
      +'<div class="q">'+esc(s.subject_id)+' '+pill(s.signal)+'</div>'
      +'<div class="meta"><span class="cov"><i style="width:'+cov+'%"></i></span><span>'+cov+'%</span>'
      +'<span>ev '+s.evidence_count+' · 독립 '+s.independent_source_count+'</span></div></div>';
  }).join('')||empty('조사 미선택','matching subject 없음');
  document.querySelectorAll('#subq-list .subq').forEach(el=>el.onclick=()=>selectSubject(el.dataset.subj));
  $('#type-chips').innerHTML=(seed.entity_types||[]).map(t=>
    '<span class="chip"><span class="sw" style="background:var(--on-surface)"></span>'+esc(t.label)+' · '+t.count+'</span>'
  ).join('')||'<span class="muted">entity 없음</span>';
  $('#map-sub').textContent='Subjects · '+(seed.subjects||[]).length;
}

function edgeColor(t){
  const x=(t||'').toLowerCase();
  if(x==='supports') return '#45E06F';
  if(x==='contradicts') return '#E05252';
  if(x==='qualifies') return '#FFB13B';
  if(x.indexOf('same')>=0) return '#A78BFA';
  return '#59636A';
}

function renderGraph(){
  if(!sg){
    $('#wt-svg').innerHTML='';
    $('#wt-list').innerHTML=empty('조사 미선택','Campaign Map 에서 subject 를 고르면 War Table 이 점등됩니다.');
    return;
  }
  const ents=sg.entities||[], claims=sg.claims||[], evs=sg.evidence||[], rels=sg.relationships||[];
  const nodes=[];
  ents.forEach(e=>nodes.push({id:e.id,kind:'entity'}));
  claims.forEach(c=>nodes.push({id:c.id,kind:'claim'}));
  evs.forEach(e=>nodes.push({id:e.id,kind:'evidence'}));
  (sg.extra||[]).forEach(n=>{if(!nodes.some(x=>x.id===n.id)) nodes.push(n);});
  const W=900,H=280,cx=W/2,cy=H/2, pos={}, seedId=sg.entity||(ents[0]&&ents[0].id);
  if(seedId) pos[seedId]=[cx,cy];
  nodes.filter(n=>n.id!==seedId).forEach((n,i)=>{
    const a=(Math.PI*2*i)/Math.max(nodes.length-1,1)-Math.PI/2;
    const r=n.kind==='evidence'?110:90;
    pos[n.id]=[cx+Math.cos(a)*r, cy+Math.sin(a)*r];
  });
  const edges=rels.map(rl=>{
    const a=pos[rl.from], b=pos[rl.to];
    if(!a||!b) return '';
    const col=edgeColor(rl.type);
    return '<line x1="'+a[0]+'" y1="'+a[1]+'" x2="'+b[0]+'" y2="'+b[1]+'" stroke="'+col+'" stroke-width="1.5"/>'
      +'<text class="edge-label" x="'+((a[0]+b[0])/2)+'" y="'+((a[1]+b[1])/2-4)+'" text-anchor="middle">'+esc(rl.type)+'</text>';
  }).join('');
  const nd=nodes.map(n=>{
    const p=pos[n.id]||[cx,cy];
    const sel=n.id===focus, stroke=sel?'#45E06F':'#26313A', sw=sel?2.4:1.5;
    const short=esc(String(n.id).slice(0,12));
    if(n.kind==='evidence'){
      return '<g class="gn" data-id="'+esc(n.id)+'" data-kind="evidence">'
        +'<rect x="'+(p[0]-34)+'" y="'+(p[1]-18)+'" width="68" height="36" rx="6" fill="#111820" stroke="'+stroke+'" stroke-width="'+sw+'"/>'
        +'<text class="node-type" x="'+p[0]+'" y="'+(p[1]-2)+'" text-anchor="middle">Evidence</text>'
        +'<text class="node-sub" x="'+p[0]+'" y="'+(p[1]+12)+'" text-anchor="middle">'+short+'</text></g>';
    }
    const rr=n.kind==='claim'?32:28, lab=n.kind==='claim'?'Claim':'Entity';
    return '<g class="gn" data-id="'+esc(n.id)+'" data-kind="'+n.kind+'">'
      +'<circle cx="'+p[0]+'" cy="'+p[1]+'" r="'+rr+'" fill="#111820" stroke="'+stroke+'" stroke-width="'+sw+'"/>'
      +'<text class="node-type" x="'+p[0]+'" y="'+(p[1]-4)+'" text-anchor="middle">'+lab+'</text>'
      +'<text class="node-label" x="'+p[0]+'" y="'+(p[1]+10)+'" text-anchor="middle">'+short+'</text></g>';
  }).join('');
  $('#wt-svg').innerHTML=edges+nd;
  document.querySelectorAll('#wt-svg .gn').forEach(g=>g.addEventListener('click',()=>onNode(g.dataset.id,g.dataset.kind)));
  const relTxt=rels.map(rl=>esc(rl.from)+' —'+esc(rl.type)+'→ '+esc(rl.to)).join(' · ')||'관계 없음';
  $('#wt-list').innerHTML='<span class="dim">노드 '+nodes.length+' · 관계 '+rels.length+'</span><div>'+relTxt+'</div>';
}

async function onNode(id, kind){
  focus=id;
  const exp=await (await fetch('/api/graph_expand?id='+encodeURIComponent(id))).json();
  sg.extra=sg.extra||[];
  (exp.items||[]).forEach(it=>{
    const kind2=claimIds.has(it.id)?'claim':'entity';
    if(!sg.extra.some(x=>x.id===it.id)
       && !(sg.entities||[]).some(e=>e.id===it.id)
       && !(sg.claims||[]).some(c=>c.id===it.id)
       && !(sg.evidence||[]).some(e=>e.id===it.id)){
      sg.extra.push({id:it.id,kind:kind2});
    }
    if(!(sg.relationships||[]).some(r=>(r.from===id&&r.to===it.id)||(r.to===id&&r.from===it.id))){
      sg.relationships.push({from:id,to:it.id,type:it.type});
    }
  });
  renderGraph();
  if(kind==='claim'||claimIds.has(id)) await loadClaim(id);
}

async function selectSubject(subj){
  current=subj; focus=null; renderCampaign();
  const [report, graph, claims, chron]=await Promise.all([
    fetch('/api/report?subject='+encodeURIComponent(subj)).then(r=>r.json()),
    fetch('/api/graph?subject='+encodeURIComponent(subj)).then(r=>r.json()),
    fetch('/api/subject_claims?subject='+encodeURIComponent(subj)).then(r=>r.json()),
    fetch('/api/chronicle').then(r=>r.json()),
  ]);
  sg=graph.subgraph||{entities:[],claims:[],evidence:[],relationships:[]};
  sg.entity=graph.subgraph&&graph.subgraph.entity;
  sg.extra=[];
  claimIds=new Set((claims.items||[]).map(c=>c.claim_id));
  renderGraph();
  renderPredicates(report);
  renderInspectorIdle(report, claims);
  renderChronicle((chron.assertions||[]).filter(a=>a.subject_id===subj));
}

function renderPredicates(report){
  const preds=Object.entries(report.by_predicate||{}).map(([p,v])=>
    '<div class="subq"><div class="q">'+esc(p)+' · '+v.count+' claims</div>'
    +'<div class="meta"><span class="dim">predicate</span></div></div>').join('');
  const oqs=(report.open_questions||[]).map(q=>{
    const t=q.predicate?q.predicate+' ('+(q.reason||'')+')':(q.reason||'open');
    return '<div class="subq"><div class="q">'+esc(t)+'</div><div class="meta"><span class="dim">open_question</span></div></div>';
  }).join('');
  $('#pred-list').innerHTML=(preds+oqs)||'<span class="muted">predicate 없음</span>';
}

function renderInspectorIdle(report, claims){
  if(!report||report.error){
    $('#inspector-body').innerHTML=empty('claim 미선택','그래프 노드 또는 claim 목록에서 고르세요.');
    return;
  }
  const c=report.confidence||{};
  $('#inspector-body').innerHTML=
    '<div class="claim-card"><div class="kicker"><span class="badge good">Subject · '+esc(report.signal||'—')+'</span></div>'
    +'<div class="text">'+esc(report.subject_id)+'</div>'
    +'<div class="id mono">'+esc(report.id||'')+' · predicates '+Object.keys(report.by_predicate||{}).length+'</div></div>'
    +'<div class="conf"><div class="cell"><div class="num good">'+(c.value||0).toFixed(2)+'</div><div class="cap">Confidence</div></div>'
    +'<div class="cell"><div class="num">'+(c.evidence_count||0)+'</div><div class="cap">Evidence</div></div>'
    +'<div class="cell"><div class="num">'+(c.independent_source_count||0)+'</div><div class="cap">독립 출처</div></div></div>'
    +'<div class="indep">'+esc(c.basis||'독립성 근거 없음')+'</div>'
    +'<div class="sec-label">Claims</div>'
    +((claims.items||[]).map(cl=>
      '<div class="ev support" data-c="'+esc(cl.claim_id)+'" style="cursor:pointer">'
      +'<div class="top"><span class="rel">'+esc(cl.predicate)+'</span><span class="src">'+esc(cl.modality||'')+'</span></div>'
      +'<span class="span">'+esc(cl.object_literal||cl.object_id||'—')+'</span>'
      +'<div class="trail"><span>'+esc(cl.claim_id)+'</span></div></div>').join('')
      ||empty('claim 미선택','이 subject 의 claim 이 없습니다.'))
    +'<div class="sec-label">Contradicting Evidence</div><div class="ev contra">'
    +empty('반박 없음', seed.notes.contradicts||'')+'</div>'
    +'<div class="sec-label">Seer · LLM Inference</div>'
    +'<div class="seer"><div class="hd">Seer</div><div class="body">'+esc(seed.notes.seer||'')+'</div></div>';
  document.querySelectorAll('#inspector-body [data-c]').forEach(el=>el.onclick=()=>loadClaim(el.dataset.c));
}

async function loadClaim(claim){
  focus=claim; renderGraph();
  const ev=await (await fetch('/api/evidence?claim='+encodeURIComponent(claim))).json();
  const report=current?await (await fetch('/api/report?subject='+encodeURIComponent(current))).json():{};
  const items=ev.items||[];
  const trails=await Promise.all(items.map(it=>
    fetch('/api/provenance?evidence='+encodeURIComponent(it.evidence_id)).then(r=>r.json())));
  const c=report.confidence||{};
  const supports=items.map((it,i)=>{
    const tr=trails[i]&&!trails[i].error?trails[i].trail:[];
    const trailHtml=tr.map(s=>{
      if(s.step==='document') return '<a href="/archive">'+esc(s.doc_id)+'</a>';
      if(s.step==='extraction_record') return '<span>char '+s.char_start+'–'+s.char_end+'</span>';
      if(s.step==='claim') return '<span>'+esc(s.claim_id)+'</span>';
      return '<span>'+esc(s.step)+'</span>';
    }).join('<span>›</span>');
    return '<div class="ev support"><div class="top"><span class="rel">supports</span><span class="src">'+esc(it.source_doc)+'</span></div>'
      +'<span class="span">strength '+(+it.strength).toFixed(2)+' · '+esc(it.evidence_id.slice(0,16))+'…</span>'
      +'<div class="trail"><span>Trail</span><span>›</span>'+(trailHtml||'<span class="muted">trail 없음</span>')+'</div></div>';
  }).join('')||empty('근거 없음','이 claim 의 supporting evidence 가 없습니다.');
  $('#inspector-body').innerHTML=
    '<div class="claim-card"><div class="kicker"><span class="badge good">Claim</span></div>'
    +'<div class="text">'+esc(claim)+'</div><div class="id mono">'+esc(claim)+'</div></div>'
    +'<div class="conf"><div class="cell"><div class="num good">'+(c.value||0).toFixed(2)+'</div><div class="cap">Confidence</div></div>'
    +'<div class="cell"><div class="num">'+items.length+'</div><div class="cap">Evidence</div></div>'
    +'<div class="cell"><div class="num">'+(c.independent_source_count||0)+'</div><div class="cap">독립 출처</div></div></div>'
    +'<div class="indep">'+esc(c.basis||'')+'</div>'
    +'<div class="sec-label">Supporting Evidence</div>'+supports
    +'<div class="sec-label">Contradicting Evidence</div><div class="ev contra">'
    +empty('반박 없음', seed.notes.contradicts||'')+'</div>'
    +'<div class="sec-label">Seer · LLM Inference</div>'
    +'<div class="seer"><div class="hd">Seer</div><div class="body">'+esc(seed.notes.seer||'')+'</div></div>';
}

function renderChronicle(rows){
  const rail=$('#chronicle-rail');
  if(!rows.length){
    rail.innerHTML='<div class="lead"><span class="t">Chronicle</span><span class="s">Bitemporal History</span></div>'
      +empty('이력 없음','이 subject 의 assertion 이 없습니다.');
    ticks=[]; $('#time-val').textContent='TX · now';
    return;
  }
  const n=rows.length;
  const evs=rows.map((a,i)=>{
    const left=n===1?50:Math.round(8+(i/(n-1))*84);
    const lab=a.supersedes_id?'supersedes':(a.predicate||'claim');
    const date=String(a.valid_from||a.tx_from||'').slice(0,10);
    return '<div class="event" style="left:'+left+'%"><span class="lab">'+esc(lab)+'</span><span class="pin"></span><span class="date">'+esc(date)+'</span></div>';
  }).join('');
  rail.innerHTML='<div class="lead"><span class="t">Chronicle</span><span class="s">Bitemporal History</span></div>'
    +'<div class="rail"><div class="line"></div>'+evs+'</div>';
  ticks=rows.map(a=>a.valid_from).filter(Boolean);
  const slider=$('#time-slider');
  if(slider){
    slider.max=String(Math.max(ticks.length-1,0));
    slider.value=slider.max;
    $('#time-val').textContent=String(ticks[ticks.length-1]||'TX · now').slice(0,10);
  }
}

async function onTime(i){
  if(!ticks.length||!current) return;
  const v=ticks[i];
  $('#time-val').textContent=String(v).slice(0,10);
  const r=await (await fetch('/api/chronicle?valid_at='+encodeURIComponent(v))).json();
  renderChronicle((r.assertions||[]).filter(a=>a.subject_id===current));
}

(async()=>{
  seed=await (await fetch('/api/table')).json();
  renderCampaign();
  $('#inspector-body').innerHTML=empty('claim 미선택','Campaign Map 에서 subject 를 고르세요.');
  $('#wt-list').innerHTML=empty('조사 미선택','Campaign Map 에서 subject 를 고르면 War Table 이 점등됩니다.');
  const inp=document.querySelector('header .search input');
  if(inp) inp.addEventListener('input',e=>{filter=e.target.value;renderCampaign();});
  const sl=$('#time-slider');
  if(sl) sl.addEventListener('input',e=>onTime(+e.target.value));
  // Chronicle 딥링크 → as-of URL 파라미터 부트스트랩 (bitemporal 참조, §1.3).
  const params=new URLSearchParams(location.search);
  const focusSubj=params.get('subject');
  const av=params.get('as_of_valid')||params.get('valid_at');
  if(av) $('#time-val').textContent='as-of '+av.slice(0,10);
  if(focusSubj&&seed.subjects.some(s=>s.subject_id===focusSubj)) selectSubject(focusSubj);
  else if(seed.subjects&&seed.subjects[0]) selectSubject(seed.subjects[0].subject_id);
})();
</script>
    """,
    "Orc Citadel — War Table (조사 그래프)")

# --- Hall of Witnesses — 증거 검사·원문 왕복 (`/witnesses`). ---
PAGE_WITNESSES = shell(
    "/witnesses",
    """<div class="wit-layout">
  <section class="panel" id="witness-claims">
    <div class="panel-head"><h2>Claims</h2><span class="sub" id="wit-sub">—</span></div>
    <div class="panel-body" id="claim-list"></div>
  </section>
  <section class="panel" id="witness-prov">
    <div class="panel-head"><h2>Evidence &amp; Provenance</h2><span class="sub" id="prov-sub">claim 미선택</span></div>
    <div class="mid-body" id="prov-body"></div>
  </section>
  <section class="panel doc-panel" id="witness-doc">
    <div class="doc-toolbar"><span class="dmeta mono" id="doc-meta">원문 미선택</span><div class="grow"></div></div>
    <div class="doc-scroll" id="doc-body"></div>
  </section>
</div>
<div class="roundtrip" id="roundtrip">
  <span class="lead">Round-trip</span>
  <span class="hop"><span class="n">1</span> Claim 선택</span><span class="arr">→</span>
  <span class="hop"><span class="n">2</span> Evidence · Trail</span><span class="arr">→</span>
  <span class="hop"><span class="n">3</span> 원문 span 하이라이트</span>
  <span class="goal">결과 → 원문 3-hop 이내 · provenance 완전 (§3-2)</span>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}
function empty(trig,msg){return '<div class="empty-state"><div class="trig">'+esc(trig)+'</div><p>'+esc(msg)+'</p></div>';}
let claims=[], selected=null, evidence=[], modalityFilter='';

function modBadge(m){const k={'fact':'good','asserted':'','opinion':'warn','prediction':'uncert'}[m]||'';return '<span class="badge '+k+'">'+esc(m||'')+'</span>';}

async function loadClaims(){
  const t=await (await fetch('/api/table')).json();
  claims=[];
  for(const s of t.subjects){
    const c=await (await fetch('/api/subject_claims?subject='+encodeURIComponent(s.subject_id))).json();
    for(const it of (c.items||[])){
      const ev=await (await fetch('/api/evidence?claim='+encodeURIComponent(it.claim_id))).json();
      const conf=await (await fetch('/api/report?subject='+encodeURIComponent(s.subject_id))).json();
      claims.push({subject_id:s.subject_id, value:(conf.confidence||{}).value||0,
        independent:(conf.confidence||{}).independent_source_count||0, ...it, evidence:(ev.items||[])});
    }
  }
  renderClaims();
  if(claims.length) selectClaim(claims[0].claim_id);
}

function renderClaims(){
  const shown=claims.filter(c=>!modalityFilter||c.modality===modalityFilter);
  $('#wit-sub').textContent='전체 · '+claims.length;
  $('#claim-list').innerHTML=shown.map(c=>
    '<div class="claim-row'+(c.claim_id===selected?' active':'')+'" data-c="'+esc(c.claim_id)+'">'
    +'<div class="q">'+esc(c.predicate)+' · '+esc(c.object_literal||c.object_id||'—')+'</div>'
    +'<div class="cid">'+esc(c.claim_id)+'</div>'
    +'<div class="foot">'+modBadge(c.modality)+'<span class="cmini"><b>'+(+c.value).toFixed(2)+'</b></span></div></div>'
  ).join('')||empty('claim 미선택','표시할 claim 이 없습니다.');
  document.querySelectorAll('#claim-list .claim-row').forEach(r=>r.onclick=()=>selectClaim(r.dataset.c));
}

async function selectClaim(cid){
  selected=cid; renderClaims();
  const c=claims.find(x=>x.claim_id===cid)||{};
  $('#prov-sub').textContent=cid;
  const ev=await (await fetch('/api/evidence?claim='+encodeURIComponent(cid))).json();
  evidence=ev.items||[];
  const trails=await Promise.all(evidence.map(it=>fetch('/api/provenance?evidence='+encodeURIComponent(it.evidence_id)).then(r=>r.json())));
  const claimStep=(trails[0]&&trails[0].trail||[]).find(s=>s.step==='claim')||{};
  $('#prov-body').innerHTML=
    '<div class="claim-card"><div class="kicker">'+modBadge(c.modality)+'<span class="badge">'+esc(c.predicate||'')+'</span></div>'
    +'<div class="text">'+esc(c.object_literal||c.object_id||'—')+'</div>'
    +'<div class="id mono">id '+esc(c.claim_id)+' · subj '+esc(c.subject_id||'')+' · ontology '+(claimStep.ontology_version||'—')+'</div></div>'
    +'<div class="conf"><div class="cell"><div class="num good">'+(+c.value).toFixed(2)+'</div><div class="cap">Confidence</div></div>'
    +'<div class="cell"><div class="num">'+evidence.length+'</div><div class="cap">Evidence</div></div>'
    +'<div class="cell"><div class="num">'+(c.independent||0)+'</div><div class="cap">독립 출처</div></div></div>'
    +'<div class="sec-label">Supporting Evidence · 지지</div>'
    +(evidence.map((it,i)=>'<div class="ev support'+(i===0?' active':'')+'" data-e="'+i+'" style="cursor:pointer"><div class="top">'
      +'<span class="rel">supports</span><span class="src">'+esc(it.source_doc)+'</span></div>'
      +'<div class="trail"><span>'+esc(it.evidence_id.slice(0,10))+'</span><span>›</span><a href="#" onclick="return false">'+esc(it.source_doc)+'</a>'
      +'<span>·</span><span>strength '+(+it.strength).toFixed(2)+'</span></div></div>').join('')
      ||empty('근거 없음','이 claim 의 supporting evidence 가 없습니다.'))
    +'<div class="sec-label">Provenance Trail · 원문 왕복</div>'
    +'<div id="prov-steps"></div>';
  document.querySelectorAll('#prov-body .ev.support').forEach(el=>el.onclick=()=>renderDoc(+el.dataset.e, trails));
  renderDoc(0, trails);
}

function renderDoc(i, trails){
  const tr=trails&&trails[i]&&trails[i].trail||[];
  const steps=tr.map((s,idx)=>{
    let fields='';
    if(s.step==='claim') fields='<span>predicate <b>'+esc(s.predicate||'')+'</b></span><span>ontology <b>'+esc(s.ontology_version||'—')+'</b></span>';
    else if(s.step==='extraction_record') fields='<span>segment <b>'+esc(s.segment_id||'')+'</b></span><span>char <b>'+s.char_start+'–'+s.char_end+'</b></span>';
    else if(s.step==='document') fields='<span>doc_id <b>'+esc(s.doc_id||'')+'</b></span>';
    const val=s.claim_id||s.segment_id||s.doc_id||s.step;
    return '<div class="prov-step"><div class="prov-rail"><span class="node"></span>'+(idx<tr.length-1?'<span class="link"></span>':'')+'</div>'
      +'<div class="prov-main"><div class="lbl">'+esc(s.step)+'</div><div class="val mono">'+esc(val)+'</div>'
      +'<div class="fields">'+fields+'</div></div></div>';
  }).join('')||empty('trail 없음','provenance 데이터가 없습니다.');
  $('#prov-steps').innerHTML=steps;
  const docStep=tr.find(s=>s.step==='document');
  const extStep=tr.find(s=>s.step==='extraction_record');
  if(docStep) fetchDoc(docStep.doc_id, extStep); else $('#doc-body').innerHTML=empty('원문 없음','document step 없음');
}

async function fetchDoc(docId, extStep){
  const d=await (await fetch('/api/document?doc='+encodeURIComponent(docId))).json();
  $('#doc-meta').textContent=docId+' · segments '+(d.segments||[]).length+(d.available===false?' (unavailable)':'');
  if(!d.segments||!d.segments.length){$('#doc-body').innerHTML=empty('원문 미가동','normalized 존 세그먼트 없음 (honest-gap)');return;}
  // extraction segment_id=`{doc}#p{n}` vs normalized=`{doc}#p0.s{n}` — 서로 다른 축.
  // 마지막 숫자 인덱스만 뽑아 normalized 세그먼트의 ord 와 대응 (char 오프셋은 세그 text 기준).
  const ordM=extStep&&/(\d+)$/.exec(extStep.segment_id||'');
  const targetOrd=ordM?(+ordM[1]):null;
  const seg=(targetOrd!=null)?(d.segments.find(s=>s.ord===targetOrd)||null):null;
  const title=(d.documents&&d.documents[0]&&d.documents[0].title)||docId;
  const body=d.segments.map(s=>{
    const isTarget=seg&&s.ord===seg.ord;
    let inner=esc(s.text);
    if(isTarget&&extStep){
      const a=s.text.slice(0,extStep.char_start), hi=s.text.slice(extStep.char_start,extStep.char_end), b=s.text.slice(extStep.char_end);
      inner=esc(a)+'<span class="hl support">'+esc(hi)+'<span class="off"> [supports]</span></span>'+esc(b);
    }
    return '<p><span class="off">[p'+s.ord+' · '+s.kind+']</span> '+inner+'</p>';
  }).join('');
  $('#doc-body').innerHTML='<div class="parch"><div class="doc-title">'+esc(title)+'</div>'+body
    +'<div class="doc-legend dim" style="margin-top:12px"><span class="hl support">■</span> supports 하이라이트</div></div>';
}

(async()=>{await loadClaims();
  const chips=['fact','asserted','opinion','prediction'];
  $('#claim-list').insertAdjacentHTML('beforeend','<div class="sec-label">Modality</div>'
    +chips.map(m=>'<span class="chip" data-m="'+m+'"><span class="sw" style="background:var(--primary)"></span>'+m+'</span>').join(''));
  document.querySelectorAll('#claim-list .chip').forEach(ch=>ch.onclick=()=>{modalityFilter=(modalityFilter===ch.dataset.m?'':ch.dataset.m);renderClaims();});
})();
</script>
    """,
    "Orc Citadel — Hall of Witnesses (증거 검사)")


# --- Council Chamber — 조사 보고서 조회 (`/council`). ---
PAGE_COUNCIL = shell(
    "/council",
    """<div class="cncl-grid">
  <section class="panel">
    <div class="panel-head"><h2>Subjects</h2><span class="sub" id="cncl-sub">—</span></div>
    <div class="panel-body" id="council-subjects"></div>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>Investigation Report</h2><span class="sub">get_investigation_report</span></div>
    <div class="panel-body" id="council-report"></div>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>Stopping · Cost · Audit</h2><span class="sub">read-only</span></div>
    <div class="panel-body" id="council-stop"></div>
  </section>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}
function empty(trig,msg){return '<div class="empty-state"><div class="trig">'+esc(trig)+'</div><p>'+esc(msg)+'</p></div>';}
function pill(s){return s==='high_confidence'?'<span class="pill hi">high</span>':s==='contradicted'
  ?'<span class="pill contradicted">contradicted</span>':s==='low_evidence'?'<span class="pill lo">low evidence</span>'
  :'<span class="pill normal">normal</span>';}
let subjects=[];

function bar(v,color){return '<span class="bar"><i style="width:'+Math.max(2,v*100)+'%;background:'+(color||'var(--primary)')+'"></i></span>'+(v*100).toFixed(0)+'%';}

async function load(){
  const t=await (await fetch('/api/table')).json();
  subjects=t.subjects||[];
  $('#cncl-sub').textContent='랭킹 · '+subjects.length;
  $('#council-subjects').innerHTML=subjects.map(s=>
    '<div class="subq'+(s.subject_id===current?' active':'')+'" data-s="'+esc(s.subject_id)+'"><div class="q">'
    +esc(s.subject_id)+' '+pill(s.signal)+'</div><div class="meta"><span>value '+(+s.value).toFixed(2)+'</span><span>ev '+s.evidence_count+'</span></div></div>'
  ).join('')||empty('subject 없음','랭킹 대상이 없습니다.');
  document.querySelectorAll('#council-subjects .subq').forEach(el=>el.onclick=()=>select(el.dataset.s));
  if(subjects[0]) select(subjects[0].subject_id);
}
let current=null;

async function select(subj){
  current=subj;
  document.querySelectorAll('#council-subjects .subq').forEach(el=>el.classList.toggle('active',el.dataset.s===subj));
  const r=await (await fetch('/api/council?subject='+encodeURIComponent(subj))).json();
  if(r.error){$('#council-report').innerHTML=empty('보고서 없음',esc(subj));return;}
  const c=r.confidence||{}, d=c.dimensions||{};
  const preds=Object.entries(r.by_predicate||{}).map(([p,v])=>'<div class="arow"><div class="al"><span class="an">'+esc(p)+'</span>'
    +'<span class="as">count '+v.count+' · 독립 '+v.independent_source_count+' · max '+(+v.max_value).toFixed(2)+'</span></div></div>').join('');
  const oq=(r.open_questions||[]).map(q=>'<div class="arow"><div class="al">미결 · '+esc(q.predicate||'')+'<span class="as">'+esc(q.reason||'')+'</span></div></div>').join('');
  $('#council-report').innerHTML=
    '<div class="claim-card"><div class="kicker">'+pill(r.signal)+'<span class="badge">'+esc(r.id||'')+'</span></div>'
    +'<div class="text">'+esc(r.subject_id)+'</div></div>'
    +'<div class="sec-label">결론 · Conclusion</div>'
    +'<p class="dim">'+esc(c.basis||'')+'</p>'
    +'<div class="conf"><div class="cell"><div class="num good">'+(+c.value||0).toFixed(2)+'</div><div class="cap">Confidence</div></div>'
    +'<div class="cell"><div class="num">'+(c.evidence_count||0)+'</div><div class="cap">Evidence</div></div>'
    +'<div class="cell"><div class="num">'+(c.independent_source_count||0)+'</div><div class="cap">독립 출처</div></div></div>'
    +'<div class="sec-label">by_predicate</div>'+(preds||'<span class="muted">없음</span>')
    +(oq?'<div class="sec-label">open_questions</div>'+oq:'');
  const ex=r.execution||{};
  $('#council-stop').innerHTML=
    '<div class="sec-label">종료 조건 · Stopping</div>'
    +'<div class="formula">STOP = ( A ∧ B ∧ C ) ∨ D · <span class="muted">runtime 상태 미영속</span></div>'
    +'<div class="cond"><div class="ct"><span class="ck">A</span><span class="cn">evidence coverage</span><span class="cv">'+(d.coverage||0).toFixed(2)+'</span></div>'
    +'<div class="bar"><i style="width:'+Math.max(2,(d.coverage||0)*100)+'%;background:var(--signal-amber)"></i></div></div>'
    +'<div class="cond"><div class="ct"><span class="ck">B</span><span class="cn">support</span><span class="cv">'+(d.support||0).toFixed(2)+'</span></div>'
    +'<div class="bar"><i style="width:'+Math.max(2,(d.support||0)*100)+'%;background:var(--primary)"></i></div></div>'
    +'<div class="cond"><div class="ct"><span class="ck">C</span><span class="cn">contradiction</span><span class="cv">'+(d.contradiction||0).toFixed(2)+'</span></div>'
    +'<div class="bar"><i style="width:'+Math.max(2,(d.contradiction||0)*100)+'%;background:var(--error)"></i></div></div>'
    +'<div class="sec-label">Cost</div>'
    +'<div class="cost-grid"><div class="cell"><div class="num">—</div><div class="cap">llm_usd</div></div>'
    +'<div class="cell"><div class="num">—</div><div class="cap">tokens</div></div></div>'
    +'<p class="dim">'+esc(ex.note||'조사 실행(쓰기)은 범위 밖 — 기존 결론 조회만 (honest-gap §6.2)')+'</p>'
    +'<div class="sec-label">Audit</div>'
    +'<div class="arow"><div class="al">'+(r.audit&&r.audit.passed!==undefined?(r.audit.passed?'<span class="pill hi">PASS</span>':'<span class="pill lo">FAIL</span>'):'<span class="pill normal">조회만</span>')
    +'<span class="as">evidence-first 게이트 — 조사 실행 시에만 산출</span></div></div>';
}
load();
</script>
    """,
    "Orc Citadel — Council Chamber (조사 보고서)")


# --- Citadel Gate — 홈/진입 대시보드 (`/`). ---
PAGE_GATE = shell(
    "/",
    """<h2>🗄️ 시스템 존 요약 <span class="dim">(raw / normalized / curated — 실측)</span></h2>
<div class="grid" id="zones"></div>

<h2>🏰 Citadel Spaces <span class="dim">(공간 quick-enter)</span></h2>
<div class="grid" id="gate-spaces"></div>

<h2>🎯 Campaign · Subject 랭킹 <span class="dim">(S31 · coverage + value + 독립출처 봉투)</span></h2>
<div class="grid" id="gate-cards"></div>

<h2>🚦 신호 분포 <span class="dim">(contradicted · low_evidence · high_confidence · normal)</span></h2>
<div class="card" id="signals"></div>

<script>
const $=s=>document.querySelector(s);
const dark=b=>{const w=Math.max(2,Math.round(b*140));const x=Math.min(255,Math.round(b*60+40));
  return `linear-gradient(90deg,#0b3a2e 0%,rgb(${x},${Math.round(180*b+40)},${Math.round(120*b+40)}) ${w}%)`};
const pill=s=>s==='high_confidence'?'<span class="pill hi">high</span>':s==='contradicted'
  ?'<span class="pill contradicted">contradicted</span>':s==='low_evidence'?'<span class="pill lo">low evidence</span>'
  :'<span class="pill normal">normal</span>';
const valBar=v=>'<span class="bar"><i style="width:'+Math.max(2,v*100)+'%;background:'+dark(v)+'"></i></span>'+(v*100).toFixed(0)+'%';
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

(async()=>{
  const r=await (await fetch('/api/gate')).json();
  $('#zones').innerHTML=[
    ['raw', r.raw_doc_count+' docs', (r.raw_sources||[]).length+' source'],
    ['normalized', r.normalized_counts.documents+' docs', r.normalized_counts.segments+' segments'],
    ['curated', r.curated.assertions+' assertions', r.curated.entities+' entities · '+r.curated.mentions+' mentions'],
    ['dedup', r.curated.dup_clusters+' clusters', ''],
  ].map(z=>`<div class="card"><div style="font-size:15px;font-weight:700">${esc(z[0])}</div>
    <div style="font-size:13px;margin-top:4px">${esc(z[1])}</div><div class="dim">${esc(z[2])}</div></div>`).join('');

  const spaces=[['Citadel Gate','본부 · Home','/'],['War Table','조사 · 그래프','/table'],
    ['Hall of Witnesses','증거 검사','/witnesses'],['Council Chamber','조사 보고서','/council'],
    ['Watchtower','수집 관제','/watchtower'],['Grand Archive','문서 탐색','/archive'],
    ['Chronicle Vault','시간 탐색','/chronicle'],['Signal Spire','알림 센터','/spire']];
  $('#gate-spaces').innerHTML=spaces.map(s=>`<a class="card" href="${s[2]}" style="text-decoration:none;color:inherit">
    <div style="font-size:14px;font-weight:700">${esc(s[0])}</div><div class="dim">${esc(s[1])}</div></a>`).join('');

  const t=await (await fetch('/api/table')).json();
  $('#gate-cards').innerHTML=(t.subjects||[]).slice(0,5).map(x=>{
    const cov=Math.round((x.coverage||0)*100);
    return `<div class="card"><div style="display:flex;justify-content:space-between;align-items:center">
      <b style="font-size:13px">${esc(x.subject_id)}</b>${pill(x.signal)}</div>
      <p style="margin:8px 0 4px">value <b>${valBar(x.value)}</b></p>
      <p class="dim">coverage <span class="bar"><i style="width:${cov}%"></i></span>${cov}% · 근거 ${x.evidence_count} · 독립 ${x.independent_source_count}</p>
      <p class="dim">${Object.entries(x.predicates||{}).map(([p,c])=>`<span class="badge">${esc(p)}×${c}</span>`).join(' ')}</p>
      <p><a href="/table">War Table ›</a> · <a href="/witnesses">Witnesses ›</a></p></div>`;
  }).join('')||'<span class="muted">subject 없음</span>';

  const sig=Object.entries(r.signal_distribution||{}).map(([k,v])=>`<span class="badge">${pill(k)} ${esc(k)} <b>${v}</b></span>`).join(' ')||'<span class="muted">정보 없음</span>';
  $('#signals').innerHTML=sig;
})();
</script>
    """,
    "Orc Citadel — Citadel Gate (진입 대시보드)")


# --- Watchtower — 수집 관제 (`/watchtower`). ---
PAGE_WATCHTOWER = shell(
    "/watchtower",
    """<h2>🛰️ 수집 관제 요약 <span class="dim">(raw 실측 + normalized publication_time 기준 신선도)</span></h2>
<div class="grid" id="wt-tiles"></div>

<h2>📡 Source 상태 <span class="dim">(raw 존 · source × 문서 수 · source_type)</span></h2>
<div class="card"><table id="sources"></table></div>

<h2>🛎️ SLO 판정표 <span class="dim">(nightly 5 — 관측 미누적 → 전항 not-measured, 정직)</span></h2>
<div class="card"><table id="slo"></table></div>

<h2>📈 Error Budget <span class="dim">(위반/측정 — 측정 없음이면 ratio None)</span></h2>
<div class="card" id="budget"></div>

<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

(async()=>{
  const r=await (await fetch('/api/watchtower')).json();
  const f=r.freshness||{}, srcs=r.sources||[], active=srcs.filter(s=>s.doc_count>0).length;
  $('#wt-tiles').innerHTML=[
    ['Sources', srcs.length+' · active '+active, 'raw 존 실측'],
    ['Freshness', f.measured?('median '+f.median_age_min+'m · max '+f.max_age_min+'m'):'not-measured',
      f.measured?('n='+f.n):esc(f.note||'')],
    ['Documents', srcs.reduce((a,s)=>a+s.doc_count,0), 'raw total'],
  ].map(t=>`<div class="card"><div class="dim">${esc(t[0])}</div>
    <div style="font-size:18px;font-weight:700;margin:4px 0">${esc(t[1])}</div>
    <div class="dim">${esc(t[2]||'')}</div></div>`).join('');

  $('#sources').innerHTML='<tr><th>Source</th><th>type</th><th>문서 수</th></tr>'+
    srcs.map(s=>`<tr><td>${esc(s.source_id)}</td><td><span class="badge">${esc(s.source_type)}</span></td>
      <td>${s.doc_count}</td></tr>`).join('')||'<span class="muted">source 없음</span>';

  const sl=(r.slo.nightly_slos||[]).map(x=>`<tr><td>${esc(x.slo_id)}</td>
    <td><span class="pill lo">${esc(x.classified)}</span></td><td class="dim">${esc(x.reason)}</td></tr>`).join('');
  $('#slo').innerHTML='<tr><th>SLO</th><th>판정</th><th>이유</th></tr>'+sl;

  const eb=r.slo.error_budget||{};
  $('#budget').innerHTML=`<p>violations <b>${eb.violations}</b> · measured <b>${eb.measured_count}</b>
    · violation_ratio <b>${eb.violation_ratio===null?'<span class="na">not-measured (분모 제외)</span>':eb.violation_ratio}</b></p>`;
})();
</script>
    """,
    "Orc Citadel — Watchtower · Ingestion Monitor (수집 관제)")


# --- Signal Spire — 알림 센터 (`/spire`). ---
PAGE_SPIRE = shell(
    "/spire",
    """<h2>🔔 5 종 트리거 카탈로그 <span class="dim">(정본 signal_spire.TRIGGER_TYPES)</span></h2>
<div class="card"><table id="spire-triggers"></table></div>

<h2>🕯️ 알림 피드 <span class="dim">(실 점화 없음 → 정직 빈 상태, §6.2)</span></h2>
<div class="card" id="feed"></div>

<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

(async()=>{
  const r=await (await fetch('/api/spire')).json();
  $('#spire-triggers').innerHTML='<tr><th>Trigger</th><th>의미</th><th>점화</th></tr>'+
    (r.trigger_catalog||[]).map(t=>`<tr><td><code>${esc(t.trigger)}</code></td><td>${esc(t.description)}</td>
      <td><span class="pill normal">0 · not-fired</span></td></tr>`).join('');
  $('#feed').innerHTML='<div class="empty-state">'
    +'<img src="/assets/img/empty-spire.png" alt="" class="empty-art">'
    +'<div class="trig">새 알림 없음</div>'
    +'<p>'+esc(r.note)+'</p><p class="dim">'+esc(r.fire_once_rule)+'</p></div>';
})();
</script>
    """,
    "Orc Citadel — Signal Spire · Alerts (알림 센터)")


# --- Grand Archive — 문서 탐색 (`/archive`). ---
PAGE_ARCHIVE = shell(
    "/archive",
    """<h2>🔎 Sifter <span class="dim">(source_type facet — source_id 접두사 결정적 파생)</span></h2>
<div class="card" id="archive-facets"></div>

<h2>📚 Normalized Documents <span class="dim">(oc.duckdb · read-only · segment 수 포함)</span></h2>
<div class="card"><table id="docs"></table></div>

<h2>📖 Codex · 문서 상세</h2>
<div class="card" id="archive-codex"><span class="muted">문서 행을 선택하세요.</span></div>

<h2>📦 Raw 존 <span class="dim">(source × 문서 수 — Atom meta/전체 page 두 형식 공존)</span></h2>
<div class="card"><table id="raw"></table></div>

<h2>♻️ Dedup Cluster <span class="dim">(curated clusters)</span></h2>
<div class="card" id="clusters"></div>

<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
const TYPE_TOK=['official','press','gov','research','exchange'];
const stype=id=>{const h=String(id||'').split('-',1)[0];return TYPE_TOK.includes(h)?h:'source';};
let docs=[], facet='';

function renderFacets(){
  const counts={};
  docs.forEach(d=>{const t=stype(d.source_id);counts[t]=(counts[t]||0)+1;});
  $('#archive-facets').innerHTML=Object.entries(counts).map(([t,n])=>
    `<span class="chip${facet===t?' active':''}" data-t="${esc(t)}" style="${facet===t?'border-color:var(--primary);cursor:pointer':'cursor:pointer'}"><span class="sw" style="background:var(--primary)"></span>${esc(t)} · ${n}</span>`).join('')||'<span class="muted">문서 없음</span>';
  document.querySelectorAll('#archive-facets .chip').forEach(c=>c.onclick=()=>{facet=facet===c.dataset.t?'':c.dataset.t;renderFacets();renderDocs();});
}

function renderDocs(){
  const shown=docs.filter(d=>!facet||stype(d.source_id)===facet);
  $('#docs').innerHTML='<tr><th>doc_id</th><th>source</th><th>type</th><th>title</th><th>segments</th><th>char_len</th><th>parser</th></tr>'+
    shown.map(d=>`<tr data-doc="${esc(d.doc_id)}" style="cursor:pointer">
      <td><code>${esc(d.doc_id)}</code></td><td>${esc(d.source_id)}</td><td><span class="badge">${esc(stype(d.source_id))}</span></td>
      <td>${esc(d.title||'')}</td><td>${d.segments}</td><td>${d.char_len}</td><td><span class="badge">${esc(d.parser_version)}</span></td></tr>`).join('')||'<span class="muted">문서 없음</span>';
  document.querySelectorAll('#docs tr[data-doc]').forEach(tr=>tr.onclick=()=>codex(tr.dataset.doc));
}

function codex(docId){
  const d=docs.find(x=>x.doc_id===docId); if(!d) return;
  $('#archive-codex').innerHTML=`<div style="font-size:15px;font-weight:700">${esc(d.title||docId)}</div>
    <p class="dim mono">${esc(d.doc_id)} · ${esc(d.parser_version)}</p>
    <div class="conf" style="margin:10px 0">
      <div class="cell"><div class="num">${d.segments}</div><div class="cap">segments</div></div>
      <div class="cell"><div class="num">${d.char_len}</div><div class="cap">char_len</div></div>
      <div class="cell"><div class="num">${esc(stype(d.source_id))}</div><div class="cap">source_type</div></div></div>
    <p class="dim">doc_id 는 내용 해시(sha256) 기반 (03 §2.1). url: <a href="${esc(d.url||'#')}" target="_blank" rel="noopener">${esc(d.url||'—')}</a></p>
    <p><a href="/witnesses">증거로 보기 ›</a> · <a href="/table">그래프에서 보기 ›</a></p>`;
}

(async()=>{
  const r=await (await fetch('/api/archive')).json();
  docs=r.normalized_documents||[];
  renderFacets(); renderDocs();
  $('#raw').innerHTML='<tr><th>source</th><th>문서 수</th></tr>'+
    (r.raw_sources||[]).map(s=>`<tr><td>${esc(s.source_id)}</td><td>${s.doc_count}</td></tr>`).join('')||'<span class="muted">raw 없음</span>';
  $('#clusters').innerHTML='<p>dedup clusters <b>'+r.dedup_clusters+'</b></p><p class="dim">'+esc(r.format_note)+'</p>';
})();
</script>
    """,
    "Orc Citadel — Grand Archive (문서 탐색)")


# --- Chronicle Vault — 시간 탐색 (`/chronicle`). ---
PAGE_CHRONICLE = shell(
    "/chronicle",
    """<h2>⏳ AS-OF 조회 <span class="dim">(valid_at · tx_at ISO datetime — 선택, 기본 현재 tx)</span></h2>
<div class="card">
  <form id="asof">
    <label>valid_at <input id="v" name="valid_at" placeholder="2026-08-01T00:00:00"></label>
    <label>tx_at &nbsp;<input id="t" name="tx_at" placeholder="2026-08-01T00:00:00"></label>
    <button type="submit">조회</button>
  </form>
</div>

<h2>🗂️ AS-OF 상태 분해 <span class="dim">(현재 믿음 vs 해당 tx 시점 믿음)</span></h2>
<div class="card" id="chron-state"></div>

<h2>📜 Assertions <span class="dim">(bitemporal 범위 + supersedes)</span></h2>
<div class="card"><table id="assertions"></table></div>

<h2>🧭 War Table 딥링크</h2>
<div class="card" id="chron-deeplink"></div>

<h2>🔗 Supersedes 체인</h2>
<div class="card" id="chain"></div>

<h2>⏪ Graph Replay <span class="dim">(postgres `graph_mutations` SoT — ADR-304)</span></h2>
<div class="card" id="replay"></div>

<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function fmt(v){return v?esc(String(v).slice(0,10)):'<span class="na">—</span>';}

async function load(qs){
  const r=await (await fetch('/api/chronicle'+qs)).json();
  $('#assertions').innerHTML='<tr><th>assertion</th><th>subject</th><th>predicate</th><th>valid_from</th><th>valid_to</th><th>tx_from</th><th>tx_to</th><th>supersedes</th></tr>'+
    (r.assertions||[]).map(a=>`<tr>
      <td><code>${esc(a.assertion_id)}</code></td><td>${esc(a.subject_id)}</td><td>${esc(a.predicate)}</td>
      <td>${fmt(a.valid_from)}</td><td>${fmt(a.valid_to)}</td><td>${fmt(a.tx_from)}</td><td>${fmt(a.tx_to)}</td>
      <td>${a.supersedes_id?`<code>${esc(a.supersedes_id)}</code>`:'<span class="na">—</span>'}</td></tr>`).join('')||'<span class="muted">조회 결과 없음</span>';
  $('#chain').innerHTML=(r.supersedes_chain||[]).map(a=>'<p><code>'+esc(a.assertion_id)+'</code> supersedes <code>'+esc(a.supersedes_id)+'</code></p>').join('')||'<span class="muted">supersedes 체인 없음</span>';
  const asof=r.as_of||{}, all=r.assertions||[];
  const current=all.filter(a=>!a.tx_to);
  const atTx=all.filter(a=>a.tx_to);
  $('#chron-state').innerHTML=`<div class="grid">
    <div class="card"><div class="dim">현재 믿음 · tx_to=∞</div><div style="font-size:18px;font-weight:700">${current.length}</div>
      <p class="dim">${current.map(a=>esc(a.predicate)).slice(0,6).join(' · ')||'—'}</p></div>
    <div class="card"><div class="dim">해당 tx 시점 대체됨 · tx_to 닫힘</div><div style="font-size:18px;font-weight:700">${atTx.length}</div>
      <p class="dim">${asof.tx_at?('as_of_tx '+esc(String(asof.tx_at).slice(0,10))):'기본 = 현재 tx'}</p></div></div>`;
  const rp=r.graph_replay||{};
  const subj=current[0]&&current[0].subject_id;
  const dlp=new URLSearchParams(); if(subj)dlp.set('subject',subj);
  if(asof.valid_at)dlp.set('as_of_valid',asof.valid_at);
  if(asof.tx_at)dlp.set('as_of_tx',asof.tx_at);
  $('#chron-deeplink').innerHTML='<p><a class="btn primary" href="/table?'+esc(dlp.toString())+'">War Table에서 이 시점 보기 ›</a></p>'
    +'<p class="dim">focus subject '+(subj?('<code>'+esc(subj)+'</code>'):'—')+' · bitemporal as-of 파라미터 전달</p>';
  $('#replay').innerHTML=rp.available
    ? '<p>정상 — mutation 수 <b>'+rp.mutation_count+'</b></p>'
    : '<p class="na">unavailable</p><p class="dim">'+esc(rp.note)+'</p>';
}

load('');
$('#asof').onsubmit=e=>{
  e.preventDefault();
  const p=new URLSearchParams();
  if($('#v').value)p.set('valid_at',$('#v').value);
  if($('#t').value)p.set('tx_at',$('#t').value);
  load('?'+p.toString());
};
</script>
    """,
    "Orc Citadel — Chronicle Vault (시간 탐색)")


# --- remaining-gaps Wave 2 병합 -----------------------------------------------
# 각 *_ext 모듈은 자기 완결(JS 는 이 페이지 전역 헬퍼를 읽기만 하고 재정의하지 않음).
# 삽입 규칙: CSS 조각은 <body> 직전, 본문 조각은 <script> 직전(페이지 본문 끝),
# JS 문 블록은 </script> 직전(페이지 부트스트랩 이후) — 페이지마다 앵커 1회 존재를
# test_viewer_ext_merge 가 봉인한다. ext 모듈은 viewer_pages 를 import 하지 않는다.
from orc_citadel import aux_ext as _aux_ext, council_ext as _council_ext
from orc_citadel import table_ext as _table_ext, witnesses_ext as _witnesses_ext

# aux 스크립트는 api()/empty() 를 전역으로 기대하나 gate/watchtower/archive/
# chronicle 페이지는 두 헬퍼가 없다 — 보강 정의(기존 정의 절대 덮어쓰지 않음).
_EXT_PRELUDE = (
    "window.api=window.api||function(p){return fetch(p).then(function(r){return r.json();});};\n"
    # 아트가 있으면 일러스트를 얹는다 (window.EMPTY_ART — shell 이 라우트별로 심는다).
    "window.empty=window.empty||function(t,m){var a=document.documentElement.dataset.emptyArt;return '<div class=\"empty-state\">'"
    "+(a?'<img src=\"/assets/img/'+a+'\" alt=\"\" class=\"empty-art\">':'')"
    "+'<div class=\"trig\">'+esc(t)+'</div><p>'+esc(m)+'</p></div>';};\n"
)


def _inject(page: str, body: str, js: str, css: str = "", prelude: str = "") -> str:
    assert page.count("<script>") == 1 and page.count("</script>") == 1, "병합 앵커 붕괴"
    if css:
        page = page.replace("<body>", css + "<body>", 1)
    page = page.replace("<script>", body + "<script>", 1)
    return page.replace("</script>", "\n" + prelude + js + "\n</script>", 1)


PAGE_TABLE = _inject(PAGE_TABLE, *_table_ext.build(), css=_table_ext.PAGE_TABLE_EXT_CSS)
_wb, _wj = _witnesses_ext.build()
PAGE_WITNESSES = _inject(PAGE_WITNESSES, _wb, _wj)
_cb, _cj = _council_ext.build()
PAGE_COUNCIL = _inject(PAGE_COUNCIL, _cb, _cj)

_ab, _as_ = _aux_ext.build()
_SEARCH_JS, _GATE_JS, _WT_JS, _AR_JS, _CH_JS = _as_
PAGE_GATE = _inject(PAGE_GATE, _ab[0], _SEARCH_JS + _GATE_JS, prelude=_EXT_PRELUDE)
PAGE_WATCHTOWER = _inject(PAGE_WATCHTOWER, _ab[1], _WT_JS, prelude=_EXT_PRELUDE)
PAGE_ARCHIVE = _inject(PAGE_ARCHIVE, _ab[2], _AR_JS, prelude=_EXT_PRELUDE)
PAGE_CHRONICLE = _inject(PAGE_CHRONICLE, _ab[3], _CH_JS, prelude=_EXT_PRELUDE)
# Spire 는 alert 영속 부재로 본문 확장 없음 (honest-gap 유지).
#
# 헤더 검색은 셸의 일부다 — 8페이지 중 2곳에서만 동작하던 것을 전부로 올린다(갭 A4).
# SEARCH_JS 는 헤더 search input 을 스스로 찾으므로 페이지별 배선이 필요 없다.
for _name in ("PAGE_TABLE", "PAGE_WITNESSES", "PAGE_COUNCIL",
              "PAGE_WATCHTOWER", "PAGE_CHRONICLE", "PAGE_SPIRE"):
    globals()[_name] = _inject(globals()[_name], "", _SEARCH_JS, prelude=_EXT_PRELUDE)

