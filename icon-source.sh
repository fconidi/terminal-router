#!/bin/bash
# Regenerates the terminal-router icon set. Run, then copy the PNGs into
# build/usr/share/icons/hicolor/<size>/apps/terminal-router.png
set -euo pipefail
cd "$(dirname "$0")"
S=1024; C=512

grad() { # grad <angle> <colors> <out>
  magick -size ${S}x${S} -define gradient:angle=$1 gradient:"$2" "$3"
}
shape() { # shape <draw-args> <out>   -> white shape on transparent
  magick -size ${S}x${S} xc:none -fill white -draw "$1" PNG32:"$2"
}
clip() { # clip <img> <shapemask> <out>
  magick "$1" \( "$2" -alpha extract \) -alpha off -compose CopyOpacity -composite PNG32:"$3"
}

# hexagon points (flat-top), radius 330
R=330; HEX=""
for i in 0 1 2 3 4 5; do
  a=$(echo "scale=8; ($i*60)*4*a(1)/180" | bc -l)
  x=$(echo "scale=2; $C + $R*c($a)" | bc -l)
  y=$(echo "scale=2; $C + $R*s($a)" | bc -l)
  HEX="$HEX $x,$y"
done

# 1 outer coin ring
grad 135 '#9df5b1-#04240e' g-ring.png
shape "circle $C,$C $C,6" m-ring.png
clip g-ring.png m-ring.png l1.png

# 2 groove (reversed light) 
grad 315 '#0a3d18-#6fd98c' g-groove.png
shape "circle $C,$C $C,58" m-groove.png
clip g-groove.png m-groove.png l2.png

# 3 recessed inner face
magick -size ${S}x${S} radial-gradient:'#22703a-#031c0a' g-inner.png
shape "circle $C,$C $C,104" m-inner.png
clip g-inner.png m-inner.png l3.png

# 4 hexagon plate + edge highlight
grad 135 '#79ef95-#0b5522' g-hex.png
shape "polygon $HEX" m-hex.png
clip g-hex.png m-hex.png l4.png
magick -size ${S}x${S} xc:none -stroke '#c9f8d6' -strokewidth 7 -fill none \
  -draw "polygon $HEX" PNG32:l4edge.png

# 5 TR monogram
magick -size ${S}x${S} xc:none -font Liberation-Sans-Bold -pointsize 330 \
  -gravity center -fill '#03210c' -annotate +7+11 'TR' -blur 0x7 PNG32:l5shadow.png
magick -size ${S}x${S} xc:none -font Liberation-Sans-Bold -pointsize 330 \
  -gravity center -stroke '#0b5522' -strokewidth 7 -fill '#ffffff' \
  -annotate +0+0 'TR' PNG32:l5.png

# 6 gloss
magick -size ${S}x${S} xc:none -fill 'rgba(255,255,255,0.30)' \
  -draw "ellipse $((C-30)),$((C-190)) 390,200 0,360" -blur 0x45 PNG32:g-gloss.png
shape "circle $C,$C $C,6" m-clip.png
magick g-gloss.png m-clip.png -compose DstIn -composite PNG32:l6.png

# 7 dark outer rim (definition on light backgrounds)
magick -size ${S}x${S} xc:none -stroke '#021707' -strokewidth 10 -fill none \
  -draw "circle $C,$C $C,12" PNG32:l7.png

# 8 specular sparkle top-right
magick -size ${S}x${S} xc:none -fill white \
  -draw "polygon 700,250 716,316 782,332 716,348 700,414 684,348 618,332 684,316" \
  -blur 0x5 PNG32:l8.png

cp l1.png acc.png
for lay in l2.png l3.png l4.png l4edge.png l5shadow.png l5.png l6.png l8.png l7.png; do
  magick acc.png "$lay" -compose over -composite PNG32:acc-next.png
  mv acc-next.png acc.png
done
mv acc.png terminal-router-1024.png
echo OK
