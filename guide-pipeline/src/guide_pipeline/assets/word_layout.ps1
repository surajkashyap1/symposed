# Asks Word how a guide lays out, for guide_docx.py. Opens the file read-only and never saves it.
#   -Mode layout : prints one line per fact
#       pages <n>
#       start <page> <bookmark>       first top-level paragraph starting on that page
#       table <page> <table> <row>    the page starts inside top-level table <table> (1-based) at <row>
#       mark <bookmark> <page>        the page each named bookmark is on (for the contents page)
#   -Mode pdf    : saves a PDF copy of the document to -Pdf
param([string]$Docx, [string]$Mode = "layout", [string]$Pdf = "")
$ErrorActionPreference = "Stop"
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open($Docx, $false, $true, $false)
  if ($Mode -eq "pdf") {
    $d.SaveAs2($Pdf, 17)
    Write-Output "pdf"
  } else {
    $d.Repaginate()
    $pages = $d.ComputeStatistics(2)
    Write-Output "pages $pages"
    for ($n = 2; $n -le $pages; $n++) {
      $r = $d.GoTo(1, 1, $n)
      $para = $r.Paragraphs.Item(1)
      $found = $null
      while ($para -ne $null) {
        $startPage = $d.Range($para.Range.Start, $para.Range.Start).Information(3)
        if ($startPage -gt $n) { break }
        if ($startPage -eq $n -and -not $para.Range.Information(12)) {
          $bm = $para.Range.Bookmarks
          for ($k = 1; $k -le $bm.Count; $k++) {
            if ($bm.Item($k).Name -like "sym*") { $found = $bm.Item($k).Name; break }
          }
          if ($found) { break }
        }
        $para = $para.Next()
      }
      if ($found) {
        Write-Output "start $n $found"
      } elseif ($r.Information(12)) {
        $table = $d.Range(0, $r.End).Tables.Count
        Write-Output ("table $n $table " + $r.Cells.Item(1).RowIndex)
      } else {
        Write-Output "none $n"
      }
    }
    foreach ($b in $d.Bookmarks) {
      if (-not ($b.Name -like "sym*")) {
        Write-Output ("mark " + $b.Name + " " + $d.Range($b.Range.Start, $b.Range.Start).Information(3))
      }
    }
  }
} catch {
  Write-Output ("error " + $_.Exception.Message)
} finally {
  foreach ($doc in @($w.Documents)) { $doc.Close([ref]0) }
  $w.Quit([ref]0)
}
