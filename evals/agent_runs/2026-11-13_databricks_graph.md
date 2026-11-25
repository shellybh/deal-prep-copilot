# תדריך הכנה לפגישה: Databricks

תאריך המחקר: 2026-11-13 · פגישה: הזדמנות מכירה · עומק: standard · אתר: databricks.com · שפות החיפוש: en, he
מטרה: פגישת מכירה ראשונה

## תקציר בעמוד אחד

- מטרת הפגישה היא פגישת מכירה ראשונה להצגת פתרונות NexaStream לצוות Databricks. _(מידע מהמשתמש)_
- Databricks מציגה צמיחה מהירה ועברה קצב הכנסות חודשי (revenue run-rate) של 7 מיליארד דולר עם שווי שוק של 190 מיליארד דולר נכון לאוגוסט 2026. [1]
- ל-NexaStream Core יש מחבר טבעי (Native Connector) מובנה ל-Databricks ותמיכה מלאה בקריאה וכתיבה של טבלאות Delta Lake. [2][3]
- הזדמנות מרכזית: שילוב NexaStream Pulse ו-Lumen מספק שכבת דשבורדים בזמן אמת (p95 של 800 מילי-שניות) ללא קוד עבור משתמשים עסקיים, המשלים את המיקוד ההנדסי של Databricks. [4][5][6] _(ניתוח AI)_
- סיכון מרכזי: חפיפה מול מוצרים פנימיים ש-Databricks מפתחת ומרחיבה במהירות כגון Genie, Unity AI Gateway ורכישת Row Zero. [1][7]
- אסטרטגיה מומלצת: למצב את NexaStream לא כתחליף ל-Databricks אלא כמנוע עיבוד בזמן אמת, מאיץ תצוגה עסקית ומחבר רב-ענני בעל תמחור קבוע וצפוי. [3][6] _(המלצה)_

## נספח מפורט

### 1. סקירת החברה
- Databricks מגדירה את עצמה כחברת Data ו-AI ומספקת פלטפורמה מאוחדת לנתונים, אנליטיקה ובינה מלאכותית. [1][8][7]
- מטה החברה ממוקם בסן פרנסיסקו, קליפורניה (160 Spear Street). [8][9]
- החברה משרתת למעלה מ-20,000 ארגונים ברחבי העולם, כולל מעל 70% מחברות Fortune 500 כגון adidas, AT&T, Bayer, Mastercard, Unilever, Microsoft ו-Apple. [8][10][4][7]
- פלטפורמת החברה משמשת את כל בעלי התפקידים בצוותי הנתונים: מהנדסי נתונים, אנליסטים, מומחי BI, מדעני נתונים ומהנדסי ML. [4] _(ודאות נמוכה)_
- Databricks הרחיבה את פעילותה בישראל ופתחה משרדים חדשים בהרצליה בהובלת ליאור צברי. [11]

### 2. התפתחויות אחרונות
- 5 בנובמבר 2026: Databricks הכריזה על פרוטוקול הקוד הפתוח OpenSharing (התפתחות של Delta Sharing) תחת קרן Linux Foundation AI & Data. [12]
- 4 בנובמבר 2026: החברה פרסמה מקרה בוחן על חברת Ubisoft המשתמשת ב-Unity Gateway לניהול וממשק מודלי AI בפיתוח משחקים. [13]
- 4 בנובמבר 2026: Databricks הציגה מדדי ביצועים מעודכנים להרצת מודלי בקוד פתוח (Open-Weight Models) על גבי הפלטפורמה שלה. [14]
- 4 בנובמבר 2026: פרסום סיפור לקוח של AkzoNobel העושה שימוש ב-Databricks Genie לקבלת תשובות עסקיות מהירות. [15]
- 23 בספטמבר 2026: Databricks הודיעה על רכישת חברת Row Zero לשילוב גליונות נתונים חיים ומנוהלים בתוך מוצר Genie. [7]

### 3. מידע פיננסי
- רבעון שני 2026 (דיווח מ-13 באוגוסט 2026): החברה חצתה קצב הכנסות שנתיוי (revenue run-rate) של 7 מיליארד דולר, המהווה צמיחה של מעל 80% משנה לשנה. [1]
- אוגוסט 2026: Databricks גייסה סבב אסטרטגי של 5 מיליארד דולר (Series L - II) לפי שווי חברה של 190 מיליארד דולר, והעלתה את סך הגיוסים המצטבר ל-32.257 מיליארד דולר ב-28 סבבים. [1][16]
- רבעון רביעי 2026 (דיווח מ-9 בפברואר 2026): החברה חצתה קצב הכנסות שנתי של 5.4 מיליארד דולר (>65% צמיחה YoY) והשלימה גיוס של כ-5 מיליארד דולר במניות לפי שווי של 134 מיליארד דולר לצד 2 מיליארד דולר באשראי. [17]
- שנת 2023: הכנסות החברה הגיעו ל-1.6 מיליארד דולר. [18] _(ודאות נמוכה)_

### 4. אנשי מפתח
- עלי גודסי (Ali Ghodsi): מייסד משותף ומנכ"ל (CEO), מוביל את החזון, האסטרטגיה והתרחבות מוצרי ה-Data & AI והשותפויות הענניות. [19][20][18]
- יון סטויקה (Ion Stoica): מייסד משותף ויו"ר פעיל (Executive Chairman). [19][21]
- פטריק ונדל (Patrick Wendell): מייסד משותף לסגן נשיא להנדסה (VP of Engineering). [19][18][22]
- רון גבריסקו (Ron Gabrisko): סמנכ"ל הכנסות ראשי (Chief Revenue Officer). [21][22] _(ודאות נמוכה)_
- ליאור צברי: מנהל הפעילות והתרחבות החברה בישראל. [11]

### 5. סקירת ענף
- שוק פלטפורמות הנתונים וה-AI מתמקד בהנגשת מידע ארגוני ובאיחוד הנדסת נתונים, אנליטיקה ו-AI תחת ארכיטקטורת Lakehouse אחת. [23][10][7]
- ארגונים מתמודדים עם פערים בהנגשת נתונים בזמן אמת ובחיבור תשתיות מורכבות למשתמשים עסקיים ללא צורך בהנדסת צינורות מורכבת. [4][5]

### 6. מודיעין תחרותי
- מתחרים ישירים וענניים בולטים בתחום האנליטיקה והנתונים כוללים את Snowflake, Google BigQuery, Amazon Redshift, Azure Synapse ופתרונות קוד פתוח כגון QuantaLake. [24][25][26][27]
- Snowflake מתחרה בפתרונות ניהול נתונים ומציעה מנוע SQL ייעודי עם הפרדה מלאה בין אחסון לעיבוד והתרחבות מהירה. [26] _(ודאות נמוכה)_
- QuantaLake מציעה מנוע Lakehouse מבוסס Apache Iceberg בעלות נמוכה ($0.90 לשעת מחשוב בגרסת הענן), הפופולרי בקרב צוותי הנדסה. [27][28]
- NexaStream מבדלת את עצמה הודות לתמיכה מלאה בריבוי עננים (AWS, Azure, GCP), מודל תמחור מנוי קבוע וצפוי, ביצועי בזמן אמת (p95 של 800 מילי-שניות) ומעל 300 מחברים טבעיים. [3][29][6]

### 7. מידע פנימי רלוונטי
- מפרט המוצר NexaStream Core כולל מחבר טבעי מובנה (Native Connector) ל-Databricks מתוך למעלה מ-300 מחברים קיימים. [2]
- NexaStream Core כולל יכולת מובנית לקריאה וכתיבה של טבלאות בפורמט Delta Lake ו-Apache Iceberg. [3]
- NexaStream Core פועל ומתחבר בצורה טבעית על גבי שלושת העננים המובילים: AWS, Microsoft Azure ו-Google Cloud. [3][6]
- מסמכי ה-CRM הפנימיים אינם מכילים נתוני ארכיטקטורה ספציפיים או היסטוריית זכיות/הפסדים ישירה מול ישות Databricks כלקוח. [2] _(ניתוח AI)_

### 8. הזדמנויות עסקיות
- **אינטגרציה טבעית עם אקו-סיסטם ה-Data וה-AI של Databricks ו-Delta Lake** (חשיבות: High) [2][3][1][17][7]
  פלטפורמת NexaStream Core כוללת מחבר טבעי (Native Connector) ל-Databricks מתוך מעל 300 מחברים [2], לצד תמיכה מובנית בקריאה וכתיבה של טבלאות Delta Lake ו-Apache Iceberg [3]. Databricks מצידה מפתחת ומרחיבה את מוצרי ה-Data וה-AI שלה כגון Delta Lake, Lakebase, Genie ו-Unity AI Gateway [1][17][7].
  - למה זה חשוב: היכולת להתחבר באופן טבעי ל-Databricks ולנהל טבלאות Delta Lake מאפשרת פריסה מהירה ללא צורך בהנדסת צינורות נתונים מורכבת מחדש.
  - איך להתייחס: להציג בפגישה את המכולל הטבעי ל-Databricks ואת התמיכה ב-Delta Lake ב-NexaStream Core, ולהדגיש חיבור מהיר לפתרונות הנתונים הקיימים בארגון.
  - נימוק הדירוג: תאימות טכנית טבעית ל-Databricks היא תנאי סף קריטי להצלחת ענף המכירות ולמימוש הפתרון בסביבת הלקוח.
- **מענה לפער בנגישות נתונים ושכבת ויזואליזציה למשתמשי קצה עסקיים** (חשיבות: Medium) [4][5][6]
  פלטפורמת Databricks מתמקדת בעיקר בצוותי הנדסת נתונים, מדעני נתונים ואנשי AI [4]. מוצרי NexaStream (כגון Pulse ו-Lumen) מספקים שכבת דשבורדים ובינה מלאכותית מובנית ללא קוד עם זמן תגובה של 800 מילי-שניות (p95) [5][6], בדומה לפתרון שיושם במקרי בוחן של ארגונים שחיפשו פתרון הכל-כלול ללא צורך ברכש BI נפרד [5].
  - למה זה חשוב: צוותים עסקיים מתקשים לעיתים לעבוד ישירות מול פלטפורמות הנדסיות מורכבות, ושילוב דשבורדים מובנים פותר פער זה.
  - איך להתייחס: להציג את NexaStream Pulse ו-Lumen כשכבת תצוגה עסקית וזמן-אמת מעל ה-Lakehouse של Databricks.
  - נימוק הדירוג: מספק ערך מוסף ברור מעבר ליכולות הליבה ההנדסיות של Databricks עבור אנליסטים ומנהלים עסקיים.

### 9. סיכונים ואתגרים
- **חפיפה מול מוצרים ורכיבים פנימיים של Databricks** (חשיבות: High) [1][7]
  Databricks מפתחת ומרחיבה בקצב מהיר פתרונות פנימיים כגון Genie (סייען AI לשאלות עסקיות), Unity AI Gateway, Lakebase, ואף רכשה את Row Zero להוספת גליונות נתונים מנוהלים [1][7].
  - למה זה חשוב: תפיסת כפילות טכנולוגית עלולה לעכב או לחסום את תהליך הרכש.
  - איך להתייחס: למצב את NexaStream לא כתחליף ל-Databricks, אלא כמנוע ניתוח ועיבוד בזמן אמת ומחבר רב-ענני המשלים את האקו-סיסטם הקיים.
  - נימוק הדירוג: אם הארגון מעדיף להסתמך בלעדית על מוצרי הבית של Databricks, הוא עשוי לראות ב-NexaStream רכיב כפול או מיותר.

### 10. אסטרטגיית הפגישה
- מטרת הפגישה היא פגישת מכירה ראשונה להצגת מוצרי NexaStream ובחינת שיתוף פעולה או רכישה בסביבת הנתונים שלהם. _(מידע מהמשתמש)_
- יש להדגיש בפגישה את המחבר הטבעי ל-Databricks ואת התמיכה המלאה ב-Delta Lake המאפשרים אינטגרציה מהירה ללא שינוי ארכיטקטורה. [2][3] _(המלצה)_
- יש להציג את NexaStream Pulse בשכבת דשבורדים בזמן אמת למשתמשים עסקיים המעניקה מענה מהיר (800ms) ללא צורך בכתיבת קוד. [4][5][6] _(המלצה)_
- יש לנהל בזהירות חששות מחפיפה למוצרי הבית של Databricks (כגון Genie ו-Unity Gateway) ולמצב את NexaStream כפתרון משלים ולא כמתחרה. [1][7] _(המלצה)_

### 11. שאלות מומלצות
- כיצד אנליסטים וצוותים עסקיים צורכים כיום נתונים מתוך סביבת Databricks, והאם קיים פער בשכבת ה-BI והדשבורדים? [5][4] _(המלצה)_
- מהם האתגרים או מורכבות העלויות שאתם חווים בניהול צינורות נתונים בזמן אמת וקריאה/כתיבה של טבלאות Delta Lake? [3][6] _(המלצה)_

### 12. צעדים מומלצים להמשך
- תיאום הדגמה טכנית (POC / Demo) של NexaStream Core בהצגת המחבר הטבעי ל-Databricks וחיבור ל-Delta Lake. [2][3] _(המלצה)_
- קיום סדנת TCO ובחינת תמחור להצגת יתרונות מודל המנוי הקבוע של NexaStream מול תמחור לפי צריכה. [5][6] _(המלצה)_

## מקורות

[1] Databricks Grows >80% YoY, Surpasses $7B Revenue Run-Rate, Scales Lakebase, Genie, and Unity AI Gateway - Databricks, databricks.com, תאריך לא ידוע, רמה 1, https://www.databricks.com/company/newsroom/press-releases/databricks-grows-80-yoy-surpasses-7b-revenue-run-rate-scales
[2] פנימי: product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Featured Integrations > Other Notable Connectors (300+ total)
[3] פנימי: product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Platform Overview
[4] Report: Databricks Business Breakdown & Founding Story | Contrary Research, research.contrary.com, תאריך לא ידוע, רמה 4, https://research.contrary.com/company/databricks
[5] פנימי: casestudy_lumos_retail.md § Case Study: Lumos Retail Group > Why We Won
[6] פנימי: battlecard_cloudnova.md § Competitive Battle Card: CloudNova Analytics > Our Strengths
[7] Databricks Acquires Row Zero, Bringing Live, Governed Spreadsheets to Genie - Databricks, databricks.com, 2026-09-23, רמה 1, https://www.databricks.com/company/newsroom/press-releases/databricks-acquires-row-zero-bringing-live-governed-spreadsheets
[8] About Databricks: The data and AI company | Databricks, databricks.com, תאריך לא ידוע, רמה 1, https://www.databricks.com/company/about-us
[9] Databricks, tavily.com, תאריך לא ידוע, רמה 4, https://tavily.com/knowledge/company/7LlnrDq1nEGX
[10] Customer Stories | Databricks, databricks.com, תאריך לא ידוע, רמה 1, https://www.databricks.com/customers
[11] חברת הדאטה Databricks מתרחבת בישראל, geektime.co.il, תאריך לא ידוע, רמה 3, https://www.geektime.co.il/flash/databricks-expands-in-israel
[12] From Delta Sharing to OpenSharing: what changed, what's next | Databricks Blog, databricks.com, 2026-11-05, רמה 1, https://www.databricks.com/blog/delta-sharing-opensharing-what-changed-whats-next
[13] Ubisoft Scales AI Coding With Unity Gateway | Databricks, databricks.com, 2026-11-04, רמה 1, https://www.databricks.com/customers/ubisoft/unity-gateway
[14] The Enterprise Case for Open-Weight Models on Databricks | Databricks Blog, databricks.com, 2026-11-04, רמה 1, https://www.databricks.com/blog/enterprise-case-open-weight-models-databricks
[15] AkzoNobel Brings Genie to the Business | Databricks, databricks.com, 2026-11-04, רמה 1, https://www.databricks.com/es/customers/akzonobel/genie
[16] Databricks Stock Price, Funding, Valuation, Revenue & Financial Statements, cbinsights.com, תאריך לא ידוע, רמה 3, https://www.cbinsights.com/company/databricks/financials
[17] Databricks Grows >65% YoY, Surpasses $5.4 Billion Revenue Run-Rate, Doubles Down on Lakebase and Genie - Databricks, databricks.com, תאריך לא ידוע, רמה 1, https://www.databricks.com/company/newsroom/press-releases/databricks-grows-65-yoy-surpasses-5-4-billion-revenue-run-rate
[18] Databricks Executive Leadership Team - Innovators in Cloud Data and AI, exa.ai, תאריך לא ידוע, רמה 4, https://exa.ai/websets/directory/databricks-executives
[19] Databricks Announces Changes in Leadership Team to Align With Rapid Growth, finance.yahoo.com, תאריך לא ידוע, רמה 3, https://finance.yahoo.com/news/databricks-announces-changes-leadership-team-140000117.html
[20] Databricks CEO, Founder, Key Executive Team, Board of Directors & Employees, cbinsights.com, תאריך לא ידוע, רמה 3, https://www.cbinsights.com/company/databricks/people
[21] Databricks Announces Changes in Leadership Team - BigDATAwire, hpcwire.com, תאריך לא ידוע, רמה 4, https://www.hpcwire.com/bigdatawire/this-just-in/databricks-announces-changes-leadership-team
[22] Databricks Executive Team | Comparably, comparably.com, תאריך לא ידוע, רמה 4, https://www.comparably.com/companies/databricks/executive-team
[23] Databricks Grows >55% YoY, Surpasses $4.8B Revenue Run-Rate, and is Raising >$4B Series L at $134B Valuation - Databricks, databricks.com, תאריך לא ידוע, רמה 1, https://www.databricks.com/company/newsroom/press-releases/databricks-surpasses-4-8b-revenue-run-rate-growing-55-year-over-year
[24] Databricks - Market Share, Competitor Insights in Big Data Analytics, 6sense.com, תאריך לא ידוע, רמה 4, https://www.6sense.com/tech/big-data-analytics/databricks-market-share
[25] Databricks competitors: 13 alternatives compared (2026), flexera.com, תאריך לא ידוע, רמה 4, https://www.flexera.com/blog/finops/databricks-competitors
[26] 7 Databricks Alternatives for 2026 (No Spark Required) | Definite, definite.app, תאריך לא ידוע, רמה 4, https://www.definite.app/blog/databricks-alternatives
[27] פנימי: battlecard_quantalake.md § Competitive Battle Card: QuantaLake > Competitor Snapshot
[28] פנימי: battlecard_quantalake.md § Competitive Battle Card: QuantaLake > Their Strengths
[29] פנימי: product_spec_integrations_security.md § Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance > Featured Integrations > Snowflake

_בדיקות איכות: 3 משפטים כלליים הוסרו._
