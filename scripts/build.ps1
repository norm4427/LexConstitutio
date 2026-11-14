# Parses the raw harvest in data/raw/, keeps constitutional-law articles,
# tags them with the topic taxonomy, and writes docs/data/articles.js.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build.ps1 [-SourcesFile scripts/sources.tsv] [-OutFile docs/data/articles.js]
param([string]$SourcesFile = 'scripts/sources.tsv', [string]$OutFile = 'docs/data/articles.js')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Add-Type -AssemblyName System.Web

$opts = [Text.RegularExpressions.RegexOptions]'IgnoreCase, Compiled'
function New-Rx($p) { [regex]::new($p, $opts) }

# ---------------------------------------------------------------- taxonomy
$taxonomy = @(
  @{ id='theory';     name='Theory & Interpretation';      parent=$null; desc='How the Constitution is read, justified, and changed.' }
  @{ id='originalism';name='Originalism';                  parent='theory'; re='originalis|original (public )?meaning|original understanding|original intent|framers.{0,3} intent' }
  @{ id='living';     name='Living & Common-Good Constitutionalism'; parent='theory'; re='living constitution|common[- ]good constitutionalism|moral reading|constitutional construction|evolving (standards|meaning)|progressive constitutionalism' }
  @{ id='method';     name='Interpretive Method & Precedent'; parent='theory'; re='constitutional interpretation|interpretive (method|theory)|textualis|stare decisis|precedent|liquidation|constitutional (theory|meaning)|tradition' }
  @{ id='history';    name='Constitutional History';       parent='theory'; re='founding|framers|ratification|constitutional convention|reconstruction|federalist (papers|no)|antebellum|anti-?federalist|eighteenth[- ]century|nineteenth[- ]century|legal history' }
  @{ id='amendment';  name='Amendment & Popular Constitutionalism'; parent='theory'; re='popular constitutionalism|article v\b|constitutional amendment|amendment process|departmentalism|constitutional politics|constitutional change' }
  @{ id='jurisprudence'; name='Jurisprudence & Legal Philosophy'; parent='theory'; re='jurisprudential|philosophy of law|general jurisprudence|analytic jurisprudence|legal (philosophy|theory|positivism|realism|process)|natural (law|rights)|positivis|\bmorality\b|moral (theory|philosophy|reading)|philosoph|\bdworkin|\brawls|h\.\s?l\.\s?a\.\s?hart|liberalism|republicanism|political theory|theory of justice' }
  @{ id='democratic'; name='Constitutionalism & Democratic Theory'; parent='theory'; re='democra(cy|tic theory|tic legitimacy)|legitimacy|constitutionalism|rule of law|popular sovereignty|self-government|consent of the governed|social contract|constitutional (culture|order|design|failure|crisis|crises|norms|hardball|rot)' }
  @{ id='general';    name='General Theory & Doctrine';    parent='theory'; re='constitutional (law|norms|legitimacy|values|order|culture|doctrine|adjudication)|legitimacy|jurisprudence|rule of law|constitutionalism|judicial (restraint|activism|role)|balancing|levels of scrutiny|tiers of scrutiny' }

  @{ id='structure';  name='Structure & Powers';           parent=$null; desc='The allocation of power among the branches and between the nation and the states.' }
  @{ id='seppowers';  name='Separation of Powers';         parent='structure'; re='separation of powers|checks and balances|unitary executive|appointments clause|removal power|removal protections|nondelegation|major questions|vesting clause' }
  @{ id='executive';  name='Executive Power & the Presidency'; parent='structure'; re='\bpresiden(t|ts|cy|tial)|twenty-(fifth|second) amendment|succession|executive (power|order|branch|privilege)|pardon|impeach|take care clause|commander in chief' }
  @{ id='congress';   name='Congressional Power';          parent='structure'; re='commerce clause|spending (clause|power)|necessary and proper|enumerated powers?|taxing power|congressional power|legislative power|section 5\b|enforcement power|congress' }
  @{ id='admin';      name='Administrative State';         parent='structure'; re='administrative (state|law|agenc)|\bagenc(y|ies)\b|chevron|loper bright|nondelegation|major questions|rulemaking|independent agenc' }
  @{ id='federalism'; name='Federalism & State Sovereignty'; parent='structure'; re='federalism|state sovereignty|tenth amendment|anti-?commandeering|commandeering|sovereign immunity|eleventh amendment|preemption|dormant commerce|states.? rights|interstate' }
  @{ id='econreg'; name='Taxation & Economic Regulation'; parent='structure'; re='\btax(es|ation|ing|payers?)?\b|income tax|public utilit|\butility rates?\b|\binsurance\b|\blicens(e|es|ing)\b|price (control|fixing|regulation)|minimum wage|\bwages?\b|labor (law|union|dispute|relations)|\bunions?\b|railroad|\bmonopol|antitrust|economic regulation|police power|business regulation|chain stores?|trading stamps|occupational' }
  @{ id='article3';   name='Judicial Power & Justiciability'; parent='structure'; re='article iii|\bstanding\b|justiciab|political question|jurisdiction[- ]stripping|judicial power|mootness|ripeness|case or controversy|cases or controversies|universal (injunction|remed)|nationwide injunction|federal courts?' }
  @{ id='court';      name='Supreme Court & Judicial Review'; parent='structure'; re='supreme court|judicial review|judicial supremacy|court[- ]packing|shadow docket|emergency docket|interim docket|equity docket|\bjustices?\b|marbury|countermajoritarian|judicial (selection|appointment|nomination)' }

  @{ id='rights';     name='Rights & Liberties';           parent=$null; desc='The Bill of Rights, the Reconstruction Amendments, and the doctrines built on them.' }
  @{ id='speech';     name='Freedom of Speech & Press';    parent='rights'; re='first amendment|free speech|freedom of (speech|the press|expression|association)|free expression|press clause|defamation|libel|hate speech|compelled speech|public forum|obscen|commercial speech|content[- ]neutral|censorship' }
  @{ id='religion';   name='Religion Clauses';             parent='rights'; re='establishment clause|free exercise|religious (liberty|freedom|exemption|accommodation)|\brfra\b|church and state|separation of church|ministerial exception|religion clauses?' }
  @{ id='guns';       name='Second Amendment';             parent='rights'; re='second amendment|bear arms|keep and bear|firearms?|\bguns?\b|bruen|heller' }
  @{ id='equality';   name='Equal Protection & Equality';  parent='rights'; re='equal protection|discriminat|race-conscious|affirmative action|segregation|desegregation|brown v\.? board|sex(ual)? (discrimination|orientation)|\bgender|suspect class|disparate impact|\bracial|\brace\b|antisubordination|anticlassification|fifteenth amendment|transgender' }
  @{ id='dueprocess'; name='Due Process & Unenumerated Rights'; parent='rights'; re='due process|privacy|abortion|\broe\b|dobbs|reproductive|same-sex marriage|right to marry|unenumerated rights|liberty interest|glucksberg|obergefell|parental rights|ninth amendment|bodily autonomy|fundamental rights?' }
  @{ id='crimpro';    name='Criminal Procedure & Punishment'; parent='rights'; re='(?<!(twenty|fifty)-)fourth amendment|search(es)? and seizure|exclusionary rule|(?<!(twenty|fifty)-)fifth amendment|self-incrimination|miranda|(?<!(twenty|fifty)-)sixth amendment|right to counsel|confrontation clause|jury trial|(?<!(twenty|fifty)-)eighth amendment|cruel and unusual|death penalty|capital punishment|double jeopardy|excessive fines|\bbail\b|warrant|policing|\bpolice\b' }
  @{ id='takings';    name='Property, Takings & Contracts';  parent='rights'; re='\btakings?\b|eminent domain|just compensation|contracts? clause|property rights|regulatory taking|economic liberty|lochner' }
  @{ id='remedies';   name='Civil Rights Remedies & State Action'; parent='rights'; re='section 1983|\b1983\b|qualified immunity|civil rights|bivens|constitutional torts?|state action|thirteenth amendment|constitutional remed' }

  @{ id='democracy';  name='Democracy & Elections';        parent=$null; desc='Voting, representation, and the law of the political process.' }
  @{ id='voting';     name='Voting Rights & Election Law'; parent='democracy'; re='voting rights|right to vote|vote dilution|\bvot(er|ers|ing)\b|ballot|election law|elections?\b|electoral|disenfranchise' }
  @{ id='districting';name='Redistricting & Representation'; parent='democracy'; re='gerrymander|redistricting|apportionment|one person,? one vote|districting|representation|electoral college' }
  @{ id='campaign';   name='Campaign Finance & Political Money'; parent='democracy'; re='campaign finance|citizens united|political (spending|money|contributions)|super pac|lobbying|corruption' }

  @{ id='frontiers';  name='Frontiers & Comparative';      parent=$null; desc='National security, citizenship, technology, and constitutional law beyond the federal Constitution.' }
  @{ id='security';   name='War Powers & National Security'; parent='frontiers'; re='war powers|national security|\bmilitary\b|foreign (affairs|relations)|treat(y|ies)|surveillance|terroris|guantanamo|emergency powers|habeas|insurrection' }
  @{ id='citizenship';name='Citizenship & Immigration';    parent='frontiers'; re='immigra|citizenship|naturaliz|birthright|\baliens?\b|noncitizen|deportation|asylum|sovereignty of tribes|tribal|indian (law|tribes|nations)' }
  @{ id='statecon';   name='State Constitutional Law';     parent='frontiers'; re='state constitution|state constitutional|state supreme court|state courts' }
  @{ id='comparative';name='Comparative & Global Constitutionalism'; parent='frontiers'; re='comparative (constitutional|law)|constitutional design|transnational|international law|global constitutionalism|canad|german|\bindia|south africa|europe|israel|constitutional courts' }
  @{ id='tech';       name='Technology & the Constitution'; parent='frontiers'; re='internet|digital|algorithm|artificial intelligence|\bai\b|social media|technolog|data privacy|platforms?\b|online|cyber' }
)
foreach ($t in $taxonomy) { if ($t.re) { $t.rx = New-Rx $t.re } }
$leaves = $taxonomy | Where-Object { $_.parent }

$conlawRx = New-Rx ('constitution|first amendment|second amendment|fourth amendment|fifth amendment|sixth amendment|eighth amendment|ninth amendment|tenth amendment|eleventh amendment|thirteenth amendment|fourteenth amendment|fifteenth amendment|bill of rights|equal protection|due process|establishment clause|free exercise|commerce clause|spending clause|separation of powers|supreme court|judicial review|article iii|article ii\b|federalism|free speech|freedom of speech|takings clause|originalis|nondelegation|appointments clause|war powers|habeas|qualified immunity|section 1983|state action|gerrymander|voting rights|unitary executive|anticommandeering|sovereign immunity|justiciab|political question')
$junkRx = New-Rx '^(front matter|back matter|table of contents|masthead|contents|index|issue information|editorial board|errata|erratum|in memoriam|dedication|foreword|preface|announcement|staff|cover|title page|annual index|board of editors|volume information|books received|notes on contributors|recent publications|books recently published)\b|^volume \d+.*(index|contents)'

$conlawJournals = @('concomm','hclq','wmborj','djclpp','scr')

function Clean([string]$s) {
  if (-not $s) { return '' }
  $s = [System.Web.HttpUtility]::HtmlDecode(($s -replace '<[^>]+>', ' '))
  $ell = [string][char]0x2026   # an ellipsis; written as a code point because Windows PowerShell reads this file as Windows-1252
  $s = $s -replace ('\[(&hellip;|' + $ell + '|\.\.\.)\]'), $ell -replace '\s+', ' '
  $s.Trim()
}
function FlipName([string]$n) {
  $n = $n.Trim()
  if ($n -match '^([^,]+),\s*(.+)$') {
    $last = $Matches[1]; $first = $Matches[2]
    if ($first -match '^(Jr\.?|Sr\.?|II|III|IV)$') { return $n }
    if ($first -match '^(.*?),\s*(Jr\.?|Sr\.?|II|III|IV)$') { return "$($Matches[1]) $last, $($Matches[2])" }
    return "$first $last"
  }
  $n
}

$sources = Get-Content $SourcesFile | Where-Object { $_.Trim() } | ForEach-Object {
  $f = $_ -split "`t"; [pscustomobject]@{ id=$f[0]; kind=$f[1]; host=$f[2]; set=$f[3]; name=$f[4] }
}

$wpAuthors = @{}
if (Test-Path data/wp_authors.tsv) {
  foreach ($line in [IO.File]::ReadAllLines((Join-Path $root 'data/wp_authors.tsv'), [Text.Encoding]::UTF8)) {
    $f = $line -split "`t"; if ($f.Count -ge 2) { $wpAuthors[$f[0]] = $f[1] }
  }
}
$wpNeeded = New-Object System.Collections.Generic.List[string]
$articles = New-Object System.Collections.Generic.List[object]
$seen = @{}
$stats = @{}

# ---------------------------------------------------------------- citation counts (OpenAlex)
function NormTitle([string]$t) { $n = ((Clean $t).ToLower() -replace '[^a-z0-9]', ''); if ($n.Length -gt 90) { $n.Substring(0, 90) } else { $n } }
$citeMap = @{}
$openalexIds = @($sources | Where-Object { $_.kind -eq 'openalex' } | ForEach-Object { $_.id })
if (Test-Path data/raw/openalex) {
  foreach ($d in Get-ChildItem data/raw/openalex -Directory) {
    if ($openalexIds -contains $d.Name) { continue }
    $tsv = Join-Path $d.FullName 'works.tsv'
    if (-not (Test-Path $tsv)) { continue }
    foreach ($line in [IO.File]::ReadAllLines($tsv, [Text.Encoding]::UTF8)) {
      $f = $line -split "`t"
      if (-not $f[0]) { continue }
      $k = "$($d.Name)|$(NormTitle $f[0])"
      if (-not $citeMap.ContainsKey($k) -or $citeMap[$k].c -lt [int]$f[2]) { $citeMap[$k] = @{ c = [int]$f[2]; y = $(if ($f[1]) { [int]$f[1] } else { $null }) } }
    }
  }
}
Write-Host "OpenAlex citation records: $($citeMap.Count)"

function Add-Article($src, $title, $authors, $abstract, $date, $url, $pdf, $subjects, $vol, $iss, $extra = $null) {
  $title = Clean $title
  if (-not $title -or $title.Length -lt 6) { return }
  if ($junkRx.IsMatch($title)) { return }
  $abstract = Clean $abstract
  $subjText = ($subjects -join ' | ')
  $isConJournal = $conlawJournals -contains $src.id
  $hits = $conlawRx.Matches($abstract) | ForEach-Object { $_.Value.ToLower() } | Select-Object -Unique
  $include = $isConJournal -or ($subjText -match 'Constitutional Law|First Amendment|Fourteenth Amendment|Supreme Court of the United States|Civil Rights and Discrimination|Election Law') -or $conlawRx.IsMatch($title) -or (@($hits).Count -ge 2)
  if (-not $include) { return }

  $key = ($src.id + '|' + ($title.ToLower() -replace '[^a-z0-9]', ''))
  if ($seen.ContainsKey($key)) { return }
  $seen[$key] = $true

  # topics: title hits weigh 3, subject hits 2, abstract hits 1
  $scores = @{}
  foreach ($t in $leaves) {
    $s = 3 * $t.rx.Matches($title).Count + 2 * $t.rx.Matches($subjText).Count + [Math]::Min(3, $t.rx.Matches($abstract).Count)
    if ($s -gt 0) { $scores[$t.id] = $s }
  }
  $topics = @($scores.GetEnumerator() | Sort-Object Value -Descending | Where-Object { $_.Value -ge 2 } | Select-Object -First 4 | ForEach-Object { $_.Key })
  if ($topics.Count -eq 0 -and $scores.Count) { $topics = @($scores.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1 | ForEach-Object { $_.Key }) }
  if ($topics.Count -eq 0) { $topics = @('general') }
  # 'general' matches phrases like "Constitutional Law" in thousands of note titles: keep it only when nothing more specific applies
  if ($topics.Count -gt 1 -and $topics -contains 'general') { $topics = @($topics | Where-Object { $_ -ne 'general' }) }

  $year = $null
  if ($date -match '(\d{4})') { $year = [int]$Matches[1] }
  if ($abstract.Length -gt 1100) { $abstract = $abstract.Substring(0, 1100) -replace '\s+\S*$', '' ; $abstract += [string][char]0x2026 }
  $kw = @($subjects | Where-Object { $src.kind -ne 'openalex' } | Where-Object { $_ -and $_.Length -lt 60 } | Select-Object -Unique -First 8)

  $o = [ordered]@{ id = ('{0}-{1}' -f $src.id, $articles.Count); t = $title; a = @($authors | Where-Object { $_ } | ForEach-Object { FlipName $_ }); y = $year; j = $src.id; ab = $abstract; u = $url }
  if ($pdf) { $o.pdf = $pdf }
  if ($vol) { $o.v = $vol }
  if ($iss) { $o.i = $iss }
  if ($topics.Count) { $o.tp = $topics }
  if ($kw.Count) { $o.kw = $kw }
  if ($extra) { foreach ($k in $extra.Keys) { if ($null -ne $extra[$k] -and $extra[$k] -ne '') { $o[$k] = $extra[$k] } } }
  if ($null -eq $o.c) {
    $ck = "$($src.id)|$(NormTitle $title)"
    if ($citeMap.ContainsKey($ck) -and (-not $year -or -not $citeMap[$ck].y -or [Math]::Abs($citeMap[$ck].y - $year) -le 2)) { $o.c = $citeMap[$ck].c }
  }
  $articles.Add([pscustomobject]$o)
  $stats[$src.id] = 1 + [int]$stats[$src.id]
}

foreach ($src in $sources) {
  $dir = Join-Path 'data/raw' $src.id
  if ($src.kind -eq 'openalex') { $dir = Join-Path 'data/raw/openalex' $src.id }
  if (-not (Test-Path $dir)) { Write-Warning "no raw data for $($src.id)"; continue }
  if ($src.kind -eq 'openalex') {
    # works.tsv is produced by scripts/openalex_flatten.pl
    $tsv = Join-Path $dir 'works.tsv'
    if (-not (Test-Path $tsv)) { Write-Warning "run scripts/openalex_flatten.pl first"; continue }
    foreach ($line in [IO.File]::ReadAllLines($tsv, [Text.Encoding]::UTF8)) {
      $f = $line -split "`t"
      if ($f.Count -lt 11 -or -not $f[0]) { continue }
      $authors = @($f[3] -split ';' | Where-Object { $_ })
      $vol = $null; $iss = $null
      if ($f[6] -match '^\d+$') { $vol = [int]$f[6] }
      if ($f[7] -match '^\d+$') { $iss = [int]$f[7] }
      $subj = @(); if ($f[9]) { $subj = @($f[9]) }
      $extra = @{ c = [int]$f[2]; fp = $(if ($f[8] -match '^\d+$') { [int]$f[8] } else { $null }) }
      Add-Article $src $f[0] $authors $f[10] $f[1] $f[4] $f[5] $subj $vol $iss $extra
    }
  } elseif ($src.kind -eq 'oai') {
    foreach ($file in Get-ChildItem $dir -Filter *.xml | Sort-Object Name) {
      $doc = New-Object xml
      try { $doc.Load($file.FullName) } catch { Write-Warning "bad xml $($file.Name)"; continue }
      foreach ($rec in $doc.GetElementsByTagName('record')) {
        $hdr = $rec.GetElementsByTagName('header')[0]
        if ($hdr.GetAttribute('status') -eq 'deleted') { continue }
        $get = { param($n) @($rec.GetElementsByTagName("dc:$n") | ForEach-Object { $_.InnerText.Trim() }) }
        $ids = & $get 'identifier'
        $landing = $ids | Where-Object { $_ -match '^https?://' -and $_ -notmatch 'viewcontent|\.pdf' } | Select-Object -First 1
        if (-not $landing -or $landing -notmatch "/$([regex]::Escape($src.set))/") { continue }
        $pdf = $ids | Where-Object { $_ -match 'viewcontent|\.pdf' } | Select-Object -First 1
        $vol = $null; $iss = $null
        if ($landing -match '/vol(\d+)/iss(\d+)') { $vol = [int]$Matches[1]; $iss = [int]$Matches[2] }
        $title = (& $get 'title') | Select-Object -First 1
        Add-Article $src $title (& $get 'creator') ((& $get 'description') -join ' ') ((& $get 'date') | Select-Object -First 1) $landing $pdf (& $get 'subject') $vol $iss
      }
    }
  } else {
    foreach ($file in Get-ChildItem $dir -Filter *.json | Sort-Object Name) {
      $raw = [IO.File]::ReadAllText($file.FullName, [Text.Encoding]::UTF8)
      try { $posts = $raw | ConvertFrom-Json } catch { Write-Warning "bad json $($file.Name)"; continue }
      foreach ($p in $posts) {
        $tags = @($p.class_list | Where-Object { $_ -like 'tag-*' } | ForEach-Object { (Get-Culture).TextInfo.ToTitleCase(($_ -replace '^tag-', '' -replace '-', ' ')) })
        $cats = @($p.class_list | Where-Object { $_ -like 'category-*' })
        $vol = $null; $iss = $null
        foreach ($c in $cats) { if ($c -match 'volume-(\d+)(-(number|issue)-(\d+))?') { $vol = [int]$Matches[1]; if ($Matches[4]) { $iss = [int]$Matches[4] } } }
        if (-not $vol -and $p.link -match 'volume-(\d+)(-(number|issue)-(\d+))?') { $vol = [int]$Matches[1]; if ($Matches[4]) { $iss = [int]$Matches[4] } }
        # WordPress post authors are site staff; real bylines come from scripts/enrich.sh (data/wp_authors.tsv)
        $authors = @()
        if ($wpAuthors.ContainsKey($p.link)) { $authors = @($wpAuthors[$p.link] -split ';' | Where-Object { $_ }) }
        $before = $articles.Count
        Add-Article $src $p.title.rendered $authors $p.excerpt.rendered $p.date $p.link $null $tags $vol $iss
        if ($articles.Count -gt $before -and -not $wpAuthors.ContainsKey($p.link)) { $wpNeeded.Add("$($src.id)`t$($p.link)") }
      }
    }
  }
}

# ---------------------------------------------------------------- book reviews
# OpenAlex often credits a reviewed book's citations to its review. Reviews of notable books show up
# under the same title in several journals, so repeated OpenAlex titles are treated as reviews.
$byTitle = $articles | Group-Object { NormTitle $_.t } | Where-Object { $_.Count -gt 1 }
$reviews = 0
foreach ($g in $byTitle) {
  foreach ($a in $g.Group) {
    if ($openalexIds -contains $a.j -and $a.t -notmatch '(?i)^(foreword|comment|note|introduction)') {
      $a.PSObject.Properties.Remove('c'); $a | Add-Member -NotePropertyName rv -NotePropertyValue 1; $reviews++
    }
  }
}
# reviews confirmed against Open Library by scripts/flag_reviews.pl (journal|normalized title)
if (Test-Path data/review_flags.tsv) {
  $confirmed = @{}
  foreach ($line in [IO.File]::ReadAllLines((Join-Path $root 'data/review_flags.tsv'), [Text.Encoding]::UTF8)) { $k = ($line -split "`t")[0]; if ($k) { $confirmed[$k] = $true } }
  foreach ($a in $articles) {
    $k = "$($a.j)|" + ((Clean $a.t).ToLower() -replace '^(the|a|an)\s+', '' -replace '[^a-z0-9]', '')
    if ($confirmed.ContainsKey($k) -and -not $a.rv) { $a.PSObject.Properties.Remove('c'); $a | Add-Member -NotePropertyName rv -NotePropertyValue 1; $reviews++ }
  }
}
Write-Host "Flagged $reviews probable book reviews"

# ---------------------------------------------------------------- output
$journals = foreach ($s in $sources) {
  [pscustomobject][ordered]@{ id=$s.id; name=$s.name; host=$s.host; count=[int]$stats[$s.id]; specialist=($conlawJournals -contains $s.id) }
}
$topicsOut = foreach ($t in $taxonomy) {
  $o = [ordered]@{ id=$t.id; name=$t.name }
  if ($t.parent) { $o.parent = $t.parent } else { $o.desc = $t.desc }
  [pscustomobject]$o
}
$payload = [ordered]@{
  generated = (Get-Date).ToString('yyyy-MM-dd')
  journals  = @($journals)
  topics    = @($topicsOut)
  articles  = @($articles | Sort-Object @{e={ if ($_.y) { $_.y } else { 0 } }; Descending=$true})
}
New-Item -ItemType Directory -Force docs/data | Out-Null
$json = $payload | ConvertTo-Json -Depth 6 -Compress
[IO.File]::WriteAllText((Join-Path $root $OutFile), "window.CL_DATA=$json;", (New-Object Text.UTF8Encoding $false))
[IO.File]::WriteAllLines((Join-Path $root 'data/wp_needed.txt'), [string[]]$wpNeeded)
Write-Host ("Wrote {0} articles; {1} WordPress articles still need bylines (run scripts/enrich.sh)" -f $articles.Count, $wpNeeded.Count)
$journals | Format-Table name, count -AutoSize | Out-String | Write-Host
