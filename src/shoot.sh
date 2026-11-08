#!/bin/zsh
# usage: shoot.sh <out.png|dom:out.dom> <width,height> <file>; a fresh profile and an alarm keep Chrome from hanging the shell.
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
P=$(mktemp -d)
if [[ $1 == dom:* ]]; then
  perl -e 'alarm 40; exec @ARGV' "$CH" --headless=new --disable-gpu --user-data-dir="$P" --virtual-time-budget=4000 --window-size="$2" --dump-dom "file://$PWD/$3" 2>/dev/null > "${1#dom:}"
else
  perl -e 'alarm 40; exec @ARGV' "$CH" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$P" --virtual-time-budget=4000 --window-size="$2" --screenshot="$PWD/$1" "file://$PWD/$3" >/dev/null 2>&1
fi
echo "exit $? for $1"
rm -rf "$P"
