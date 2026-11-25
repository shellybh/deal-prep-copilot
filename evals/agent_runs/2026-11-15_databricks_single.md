# תדריך הכנה לעסקה: Databricks

## תמצית חברה
* **פעילות ופתרונות:** Databricks היא חברה בתחום ה-Data וה-AI המציעה פלטפורמה המבוססת על קוד פתוח לאיחוד נתונים, אנליטיקה ו-AI [3]. מוצרי הפלטפורמה כוללים את Lakehouse, Unity Catalog, Genie, Lakebase, Unity Gateway, Agent Bricks ו-Lakeflow [3].
* **ביצועים פיננסיים וגודל:** החברה הגיעה לקצב הכנסות (revenue run-rate) של מעל 7 מיליארד דולר עם צמיחה של מעל 80% משנה לשנה, וגייסה לפי שווי של 190 מיליארד דולר (הוכרז באוגוסט) [1]. החברה מעסיקה מעל 12,000 עובדים ברחבי העולם [1].
* **לקוחות:** משרתת מעל 20,000 ארגונים, בהם adidas, AT&T, Bayer, Block, Mastercard, Rivian, Unilever ו-70% מחברות Fortune 500 [1], [3].
* **רכישות:** שילבה צוותים מרכישות של חברות כמו Mosaic ו-Neo [1].

## חדשות אחרונות
לא נמצאו חדשות מ-48 השעות האחרונות. להלן כתבות רקע מ-30 הימים האחרונים (רקע קודם):
* **התרחבות ומטה חדש (11 בנובמבר 2026 - רקע קודם):** Databricks הודיעה על הכפלת ההשקעה במוצרי AI ועל פתיחת מטה חדש בסן פרנסיסקו בשטח של 235,000 רגל רבוע [1].
* **השקת Genie אוטונומי (11 בנובמבר 2026 - רקע קודם):** החברה השיקה את Genie החדש – פתרון AI אוטונומי לעבודה ארגונית מורכבת [2], [3]. בין הלקוחות המשתמשים ב-Genie בייצור נמנים Zillow, Unilever, adidas, Atlassian, AstraZeneca ו-Agibank [2].
* **השקעה באירופה (10 בנובמבר 2026 - רקע קודם):** Databricks הודיעה כי תשקיע מעל 500 מיליון דולר בהולנד להאיץ פתרונות Data + AI ארגוניים [4].
* **הרחבת יכולות אימון GPU (9 בנובמבר 2026 - רקע קודם):** החברה הציגה את UCDataset (בגרסת בטא), רכיב data loader נייטיב המאיץ אימון GPU על גבי טבלאות Unity Catalog פי 10 ומפחית עלויות מחשוב [5].

## המיצוב הרלוונטי שלנו
* **מחבר מובנה (Connector):** Databricks כלולה ברשימת המחברים הבולטים הנתמכים ב-NexaStream Core Platform (מתוך מעל 300 מחברים זמינים) [product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Featured Integrations > Other Notable Connectors (300+ total)].
* **תמיכה בפורמט Delta Lake:** גרסת NexaStream Core 2026.3 כוללת תמיכה מובנית בקריאה וכתיבה (native read/write) של טבלאות Delta Lake [product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Platform Overview].
* *הערה:* לא נמצאו במסמכים הפנימיים מסמכי תחרות (Battlecards) או מקרי בוחן (Case Studies) ייעודיים המתייחסים ל-Databricks כמתחרה ישיר.

## נקודות לדיון והזדמנויות
* **אינטגרציה ועבודה עם Delta Lake:** מכיוון שפלטפורמת Databricks מבוססת על טבלאות Delta Lake [1], [3], ניתן להציג בפני הלקוח את היכולת של NexaStream Core 2026.3 לבצע קריאה וכתיבה טבעית לטבלאות Delta Lake [product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Platform Overview] ולחבר את הסביבה בטבעיות באמצעות המחבר הנתמך במוצר [product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Featured Integrations > Other Notable Connectors (300+ total)].
* **סנכרון מול כלי ה-AI של Databricks:** על רקע השקת מוצר Genie של Databricks לעבודה ארגונית [2], [3], ניתן לדון כיצד שילוב Data מ-Databricks ב-NexaStream מאפשר לצוותים ליהנות מאנליטיקה מאוחדת לצד כלי ה-AI הארגוניים של Databricks.

## סיכונים
* לא נמצאו במקורות עובדות ספציפיות המצביעות על סיכונים ידועים (אירועים, מספרים או החלטות).

## מידע חסר
* לא נמצאו חדשות מ-48 השעות האחרונות (כל הידיעות הן מ-30 הימים האחרונים).
* חסר בארגון Battlecard פנימי או Case Study ייעודי המתייחס להתמודדות תחרותית מול Databricks.
* לא נמצאו עובדות מצוטטות לגבי סיכונים תפעוליים, משפטיים או תחרותיים של Databricks.

## מקורות
### פנימי:
* product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Featured Integrations > Other Notable Connectors (300+ total)
* product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Platform Overview

### חדשות:
* [1] Databricks Doubles Down on AI Products, Opens New 235,000-Square-Foot San Francisco Headquarters | Databricks Blog, databricks.com, 11 בנובמבר 2026, https://www.databricks.com/blog/databricks-doubles-down-ai-products-opens-new-235000-square-foot-san-francisco-headquarters
* [2] The new Genie: autonomous AI for complex enterprise work | Databricks Blog, databricks.com, 11 בנובמבר 2026, https://www.databricks.com/blog/new-genie-autonomous-ai-complex-enterprise-work
* [3] Databricks Launches New Always-on Genie: Autonomous AI for Complex Enterprise Work - Databricks, databricks.com, 11 בנובמבר 2026, https://www.databricks.com/company/newsroom/press-releases/databricks-launches-new-always-genie-autonomous-ai-complex
* [4] Databricks to Invest More Than $500M in the Netherlands to Accelerate Enterprise Data + AI - Databricks, databricks.com, 10 בנובמבר 2026, https://www.databricks.com/company/newsroom/press-releases/databricks-invest-more-500m-netherlands-accelerate-enterprise-data
* [5] Accelerate GPU training on Unity Catalog tables with UCDataset | Databricks Blog, databricks.com, 9 בנובמבר 2026, https://www.databricks.com/blog/accelerate-gpu-training-unity-catalog-tables-ucdataset