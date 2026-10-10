import fs from "node:fs/promises";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = "/Users/admin/Codex/jaWikiSentenceReader/outputs/20261002-syosetu-ranked-short-stories";
const outputPath = `${outputDir}/syosetu_ranked_short_slice_of_life_2025_2026.xlsx`;

const ranked = [
  ["N2566LP",2],["N9744LT",3],["N2101LT",3],["N7035LY",3],["N5499MI",5],
  ["N4866LF",7],["N4441LM",8],["N9315KI",9],["N6182LK",13],["N7089LF",14],
  ["N5442KN",15],["N7252LH",16],["N3804KO",17],["N5982KF",47],["N3322KT",53],
  ["N2687KX",55],["N2896MB",58],["N6940LF",62],["N8506LB",73],["N7696LE",75],
  ["N6075KK",92],["N5213MJ",97],["N0346KS",98],["N5623KH",108],["N8718LC",129],
  ["N7536MN",131],["N0703KQ",135],["N0582LX",146],["N1990KN",149],["N7306LE",153],
  ["N2463MC",162],["N5563MO",171],["N7627LK",172],["N3110KO",174],["N1122LC",174],
  ["N6554LB",186],["N1279LV",188],["N6368MS",193],["N2728LP",195],["N0397MD",205],
  ["N1980KS",210],["N0696KI",221],["N9331KV",230],["N2920LU",234],["N6774MQ",235],
  ["N1197MI",236],["N1063KD",236],["N8075LZ",241],["N1231LU",241],["N6952LN",241],
  ["N7205LK",243],["N9953KT",244],["N9612LK",250],["N4673KY",251],["N5575LM",260],
  ["N8871MD",283],["N4390KU",290],["N0244KW",297]
];

async function fetchMetadata() {
  const byNcode = new Map();
  for (let i = 0; i < ranked.length; i += 15) {
    const codes = ranked.slice(i, i + 15).map(([n]) => n).join("-");
    const url = `https://api.syosetu.com/novelapi/api/?out=json&lim=500&ncode=${codes}`;
    const response = await fetch(url, { headers: { "User-Agent": "Japanese-reading-research/1.0" } });
    if (!response.ok) throw new Error(`Syosetu API returned ${response.status}`);
    const payload = await response.json();
    for (const item of payload.slice(1)) byNcode.set(item.ncode.toUpperCase(), item);
  }
  return byNcode;
}

function tokens(text) {
  return new Set(String(text || "").split(/[\s　,、/・]+/).filter(Boolean));
}

function includesAny(text, terms) {
  return terms.some((term) => text.includes(term));
}

function classify(item) {
  const hay = `${item.title || ""} ${item.keyword || ""} ${item.story || ""}`;
  const tags = tokens(item.keyword);
  const vibe = [];
  const everydaySettings = [];
  const push = (label) => { if (!vibe.includes(label)) vibe.push(label); };
  const pushSetting = (label) => {
    if (!everydaySettings.includes(label)) everydaySettings.push(label);
    push(label);
  };

  if (includesAny(hay, ["高校","高校生","高等学校","JK","学園","部活","文化祭","修学旅行"])) pushSetting("high school");
  if (includesAny(hay, ["大学","大学生","キャンパス","留学生","ゼミ","サークル"])) pushSetting("college");
  if (includesAny(hay, ["家族","家庭","ホームドラマ","姉妹","兄弟","父","母","夫","妻","旦那","姑","育児","実家","一人暮らし"])) pushSetting("home / family");
  if (includesAny(hay, ["職業もの","仕事","職場","会社","オフィス","出張","上司","同僚","新人","アルバイト","バイト","サラリーマン","OL","店員","町工場","管理栄養士"])) pushSetting("work life");

  if (tags.has("ほのぼの")) push("cozy / gentle");
  if (includesAny(hay, ["グルメ","料理","カレー","ホットケーキ","パン","丼","レシピ","食事","喫茶店"])) push("food");
  if (includesAny(hay, ["恋愛","婚約","結婚","初恋","乙女","令嬢","夫人"])) push("romance / relationships");
  if (includesAny(hay, ["田舎","季節","秋","冬","桜","ひまわり","風鈴"])) push("seasonal / rural");
  if (includesAny(hay, ["異世界","転生","転移","魔法","王女","皇帝","後宮","聖女","悪役令嬢"])) push("fantasy / isekai");
  if (includesAny(hay, ["付喪神","幽霊","妖怪","怪異","超能力","怪物","ホラー","日本人形","吸血鬼","悪魔","神様","神さま","火の神","水の神","風の神","山の神","海の神"]) || tags.has("鬼") || tags.has("神")) push("supernatural");
  if (includesAny(hay, ["ざまぁ","復讐","婚約破棄","搾取","悪意","離縁","DV","悲劇","バッドエンド","ダーク"])) push("conflict / dark");
  if (!vibe.length) push("general human drama");

  const everydayPositive = ["ほのぼの","グルメ","ホームドラマ","現代","職業もの","青春","友情","田舎","家族","喫茶店"]
    .filter((term) => hay.includes(term)).length;
  const plotHeavy = ["異世界","転生","転移","魔法","王女","皇帝","後宮","聖女","悪役令嬢","ざまぁ","復讐","婚約破棄","悪意","DV","ホラー"]
    .filter((term) => hay.includes(term)).length;
  let fit = "Mixed slice-of-life";
  if (everydayPositive >= 2 && plotHeavy === 0) fit = "Strong everyday-life fit";
  else if (plotHeavy >= 2 || (plotHeavy >= 1 && everydayPositive === 0)) fit = "日常 tag; plot-heavy";

  let setting = "Unclear / mixed";
  if (includesAny(hay, ["現代","令和","会社","職場","オフィス","町工場","高校","大学","JK","スマホ","SNS"])) setting = "Contemporary";
  else if (includesAny(hay, ["西洋","中世","王女","令嬢","皇帝","騎士"])) setting = "Western / courtly fantasy";
  else if (includesAny(hay, ["和風","日本","田舎"])) setting = "Japan / Japanese-inspired";
  if (includesAny(hay, ["異世界転生","異世界転移"])) setting = "Isekai";

  let fantasy = "None indicated";
  if (includesAny(hay, ["異世界転生","異世界転移"])) fantasy = "Isekai / reincarnation";
  else if (includesAny(hay, ["魔法","王女","皇帝","聖女","悪役令嬢","騎士"])) fantasy = "Fantasy elements";
  else if (vibe.includes("supernatural")) fantasy = "Supernatural elements";

  const contemporarySignal = tags.has("現代") || includesAny(hay, [
    "令和","高校","高校生","高等学校","JK","大学","大学生","キャンパス",
    "会社","職場","オフィス","アルバイト","バイト","サラリーマン","OL",
    "コンビニ","町工場","スマホ","SNS",
  ]);
  const explicitPastDate = /(?:18|19)\d{2}年/.test(hay);
  const excludedSetting = explicitPastDate || includesAny(hay, [
    "異世界","転生","転移","魔法","王女","王子","皇帝","後宮","聖女",
    "悪役令嬢","令嬢","騎士","伯爵","侯爵","公爵","男爵","貴族","魔王",
    "勇者","中世","近世","近代","明治","大正","昭和","江戸","戦国",
    "平安","西洋","宮廷",
  ]) || vibe.includes("supernatural");
  const darkSubject = Boolean(item.isr15 || item.iszankoku)
    || tags.has("シリアス")
    || tags.has("ダーク")
    || vibe.includes("conflict / dark")
    || includesAny(hay, [
      "ざまぁ","復讐","虐待","DV","暴力","殺人","自殺","監禁","誘拐","拷問",
      "悲劇","バッドエンド","毒親","搾取","浮気","不倫","離婚","自滅",
      "因果応報","いじめ","重病","余命","葬式","葬儀","遺体","犯罪",
      "全部失いました","両手を潰",
    ]);
  const eligible = contemporarySignal
    && everydaySettings.length > 0
    && !excludedSetting
    && !darkSubject;

  const flags = [];
  if (item.isr15) flags.push("R15");
  if (item.iszankoku) flags.push("graphic violence");
  if (item.isbl) flags.push("BL");
  if (item.isgl) flags.push("GL");
  if (includesAny(hay, ["AI直接使用","生成AI"])) flags.push("AI-use tag");

  const lengthFit = item.time <= 5 ? "Very short study read"
    : item.time <= 10 ? "Short study read"
    : item.time <= 20 ? "Medium one-shot"
    : "Longer one-shot";

  return {
    vibe: vibe.join(", "), fit, setting, fantasy,
    flags: flags.join(", ") || "None indicated",
    lengthFit, everydaySettings: everydaySettings.join(", "), eligible,
  };
}

const byNcode = await fetchMetadata();
const records = ranked.map(([ncode, bestRank]) => {
  const item = byNcode.get(ncode);
  if (!item) return { ncode, bestRank, title: "Unavailable in current Novel API" };
  const c = classify(item);
  return {
    ncode,
    bestRank,
    title: item.title,
    writer: item.writer,
    // Store the source's Japanese calendar date without allowing timezone conversion
    // to shift it to the previous day in Excel.
    published: new Date(`${item.general_firstup.slice(0, 10)}T00:00:00Z`),
    length: item.length,
    time: item.time,
    keywords: item.keyword,
    synopsis: String(item.story || "").replace(/\s+/g, " ").trim(),
    dialoguePct: item.kaiwaritu,
    points: item.global_point,
    url: `https://ncode.syosetu.com/${ncode.toLowerCase()}/`,
    ...c,
  };
}).filter((record) => record.writer && record.eligible);

const workbook = Workbook.create();
const stories = workbook.worksheets.add("Ranked stories");
const guide = workbook.worksheets.add("Guide");

stories.showGridLines = false;
stories.tabColor = "#24445C";
stories.getRange("A2:R2").merge();
stories.getRange("A2").values = [["Daily-ranked light contemporary slice-of-life one-shots, 2025–2026"]];
stories.getRange("A2:R2").format = { font: { name: "Arial", size: 15, bold: true, color: "#17324D" }, verticalAlignment: "center" };
stories.getRange("A3:R3").merge();
stories.getRange("A3").values = [[`${records.length} light contemporary metadata matches. Every row signals high school, college, home/family, or work life and excludes fantasy, supernatural, historical settings, revenge, abuse, violence, and other dark subject matter. Classifications are inferred from title, synopsis, and author keywords.`]];
stories.getRange("A3:R3").format = { font: { name: "Arial", size: 10, italic: true, color: "#566573" }, wrapText: true };
stories.getRange("A4:R4").format.borders = { bottom: { style: "thin", color: "#AAB7B8" } };

const headers = [
  "Best daily rank","N-code","Title","Author","Published","Characters","Est. minutes","Dialogue %",
  "Slice-of-life fit","Everyday setting and vibe","Setting","Fantasy level","Length fit","Content flags","Author keywords",
  "Synopsis","Story URL","Search text"
];
stories.getRange("A6:R6").values = [headers];

const rows = records.map((r) => {
  if (!r.writer) return [r.bestRank,r.ncode,r.title,"","",null,null,null,"Unavailable","","","","","","","","",`${r.ncode} unavailable`];
  const search = [r.title,r.writer,r.ncode,r.fit,r.everydaySettings,r.vibe,r.setting,r.fantasy,r.lengthFit,r.flags,r.keywords].join(" | ");
  return [r.bestRank,r.ncode,r.title,r.writer,r.published,r.length,r.time,r.dialoguePct/100,r.fit,r.vibe,r.setting,r.fantasy,r.lengthFit,r.flags,r.keywords,r.synopsis,r.url,search];
});
stories.getRange(`A7:R${6 + rows.length}`).values = rows;

const dataRange = stories.getRange(`A6:R${6 + rows.length}`);
const table = stories.tables.add(`A6:R${6 + rows.length}`, true, "RankedStoriesTable");
table.style = "TableStyleMedium2";
table.showBandedRows = true;
table.showFilterButton = true;

stories.getRange(`A6:R${6 + rows.length}`).format.font = { name: "Arial", size: 10, color: "#1E2A32" };
stories.getRange("A6:R6").format = {
  fill: "#24445C",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
stories.getRange(`A7:B${6 + rows.length}`).format.horizontalAlignment = "center";
stories.getRange(`E7:H${6 + rows.length}`).format.horizontalAlignment = "right";
stories.getRange(`E7:E${6 + rows.length}`).setNumberFormat("yyyy-mm-dd");
stories.getRange(`F7:G${6 + rows.length}`).setNumberFormat("#,##0");
stories.getRange(`H7:H${6 + rows.length}`).setNumberFormat("0%");
stories.getRange(`C7:R${6 + rows.length}`).format.verticalAlignment = "top";
stories.getRange(`C7:D${6 + rows.length}`).format.wrapText = true;
stories.getRange(`I7:P${6 + rows.length}`).format.wrapText = true;
stories.getRange(`Q7:R${6 + rows.length}`).format.wrapText = false;

stories.getRange(`I7:I${6 + rows.length}`).conditionalFormats.add("containsText", { text: "Strong", format: { fill: "#DDEBD8", font: { color: "#2F5D32", bold: true } } });
stories.getRange(`I7:I${6 + rows.length}`).conditionalFormats.add("containsText", { text: "Mixed", format: { fill: "#FFF1CC", font: { color: "#7A5700" } } });
stories.getRange(`I7:I${6 + rows.length}`).conditionalFormats.add("containsText", { text: "plot-heavy", format: { fill: "#ECEFF1", font: { color: "#546E7A" } } });
stories.getRange(`N7:N${6 + rows.length}`).conditionalFormats.add("notContainsText", { text: "None", format: { fill: "#FCE4E4", font: { color: "#9C2F2F" } } });

const widths = {
  A:12,B:11,C:36,D:18,E:12,F:12,G:11,H:11,I:24,J:34,K:22,L:23,M:21,N:20,O:42,P:52,Q:38,R:65
};
for (const [col,width] of Object.entries(widths)) stories.getRange(`${col}:${col}`).format.columnWidth = width;
stories.getRange("2:2").format.rowHeight = 25;
stories.getRange("3:3").format.rowHeight = 36;
stories.getRange("6:6").format.rowHeight = 34;
stories.getRange(`7:${6 + rows.length}`).format.rowHeight = 42;
stories.freezePanes.freezeRows(6);
stories.freezePanes.freezeColumns(2);

guide.showGridLines = false;
guide.tabColor = "#6C8E78";
guide.getRange("A2:B2").merge();
guide.getRange("A2").values = [["How to search the list"]];
guide.getRange("A2:B2").format = { font: { name: "Arial", size: 15, bold: true, color: "#17324D" } };
guide.getRange("A4:B10").values = [
  ["Field","How to use it"],
  ["Slice-of-life fit","Strong = several everyday-life signals with no excluded dark-subject signal. All current matches qualify as strong everyday-life fits."],
  ["Everyday setting and vibe","Every row includes at least one target setting: high school, college, home / family, or work life. Additional labels describe food, romance, cozy, or seasonal tones."],
  ["Setting","All included rows have a contemporary metadata signal. Fantasy, isekai, supernatural, courtly, and historical signals are excluded."],
  ["Length fit","A reading-session proxy based only on the site's estimated minutes. It does not measure Japanese difficulty."],
  ["Content flags","R15, graphic violence, serious/dark tags, revenge, abuse, exploitation, domestic violence, infidelity, and similar dark subjects are excluded."],
  ["Search text","A combined searchable field containing the title, author, N-code, classifications, and author keywords."],
];
guide.getRange("A12:B18").values = [
  ["Method / source","Details"],
  ["Strict combination","type=t; genre=302; exact keyword token 日常; output novel_type=2 and general_all_no=1."],
  ["Contemporary restriction","Requires a modern signal plus high school, college, home/family, or work-life metadata. Rejects fantasy, isekai, supernatural, courtly, and historical signals."],
  ["Light-content restriction","Rejects R15, graphic violence, serious/dark tags, revenge, abuse, exploitation, domestic violence, infidelity, and related negative-subject signals."],
  ["Ranking archive","Official overall daily top-300 morning snapshots, 2025-01-01 through 2026-10-02. 639 available dates; 2025-01-30 returned no archived data."],
  ["Novel API","https://dev.syosetu.com/man/api/"],
  ["Ranking API","https://dev.syosetu.com/man/rankapi/"],
];
guide.getRange("A4:B4").format = {
  fill: "#24445C",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
guide.getRange("A12:B12").format = {
  fill: "#24445C",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
guide.getRange("A5:B10").format = { font: { name: "Arial", size: 10, color: "#1E2A32" }, verticalAlignment: "top", wrapText: true };
guide.getRange("A13:B18").format = { font: { name: "Arial", size: 10, color: "#1E2A32" }, verticalAlignment: "top", wrapText: true };
guide.getRange("A4:B10").format.borders = { preset: "inside", style: "thin", color: "#D5DBDB" };
guide.getRange("A12:B18").format.borders = { preset: "inside", style: "thin", color: "#D5DBDB" };
guide.getRange("A:A").format.columnWidth = 24;
guide.getRange("B:B").format.columnWidth = 95;
guide.getRange("4:4").format.rowHeight = 25;
guide.getRange("5:10").format.rowHeight = 50;
guide.getRange("12:12").format.rowHeight = 25;
guide.getRange("13:18").format.rowHeight = 42;

workbook.recalculate();

const keyCheck = await workbook.inspect({
  kind: "table",
  range: "Ranked stories!A2:R12",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 18,
});
console.log(keyCheck.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "Ranked stories", range: "A1:R18", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/preview.png`, new Uint8Array(await preview.arrayBuffer()));
const guidePreview = await workbook.render({ sheetName: "Guide", range: "A1:B18", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/guide-preview.png`, new Uint8Array(await guidePreview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`OUTPUT=${outputPath}`);
console.log(`RECORDS=${records.length}; MISSING=${records.filter((r) => !r.writer).length}`);
