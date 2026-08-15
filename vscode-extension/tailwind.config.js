/**
 * Fathom — Tailwind CSS ビルド設定
 *
 * 以前は `cdn.tailwindcss.com` をWebviewから直接読み込み、この設定を index.html 内の
 * インライン `tailwind.config = {...}` で指定していた。NFR-04(ローカル通信のみ)に反する
 * ため、同じ設定でローカルビルドしたCSSを `media/vendor/tailwind.css` に出力して同梱する。
 *
 * content に index.html を指定しているので、`class="..."` だけでなくインラインJS内の
 * 文字列リテラル(例: `bg-emerald-500/30`)もスキャン対象になる。逆に言うと
 * `'bg-' + color` のような動的連結でクラス名を組み立てると生成されないため、
 * クラス名は必ず完全な文字列リテラルとして書くこと。
 */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/webview/index.html'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          bg: '#0a0a12',
          card: '#12131d',
          panel: '#191a28',
          border: '#23243a',
          text: '#e7e7f4',
          muted: '#8d8dae',
          indigo: '#818cf8',
          gold: '#fbbf24',
          green: '#34d399',
          amber: '#f59e0b',
          red: '#f87171',
        },
      },
    },
  },
  plugins: [],
};
