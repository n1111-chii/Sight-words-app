"use strict";

/* CACHE_VERSION は音声(audio/)ファイルの世代管理にのみ使う(activate時に
   古いバージョンのキャッシュを自動削除)。index.html・JSON等はfetch時に
   ネットワーク優先で取得するため、この値を上げなくても更新は反映される。 */
var CACHE_VERSION = 'v3';
var CACHE_NAME = 'taitan-cache-' + CACHE_VERSION;

var PRECACHE_URLS = [
  './',
  './index.html',
  './manifest.json',
  './fry_words.json',
  './basic_words_diff.json',
  './fry_phonics.json',
  './list1_sentences.json',
  './list2_sentences.json',
  './list3_sentences.json',
  './list4_sentences.json',
  './list5_sentences.json',
  './list6_sentences.json',
  './list7_sentences.json',
  './list8_sentences.json',
  './list9_sentences.json',
  './list10_sentences.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/apple-touch-icon.png',
  './audio-manifest.json'
];

self.addEventListener('install', function(event){
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache){
      return cache.addAll(PRECACHE_URLS).then(function(){
        return fetch('./audio-manifest.json')
          .then(function(r){ return r.ok ? r.json() : []; })
          .catch(function(){ return []; });
      }).then(function(audioUrls){
        /* 短文の音声(Leda生成)は1件ずつ個別に追加し、
           一部が取得できなくてもインストール自体は失敗させない。 */
        return Promise.all(audioUrls.map(function(url){
          return cache.add(url).catch(function(){});
        }));
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(event){
  event.waitUntil(
    caches.keys().then(function(keys){
      return Promise.all(keys.filter(function(k){ return k !== CACHE_NAME; }).map(function(k){ return caches.delete(k); }));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(event){
  if(event.request.method !== 'GET') return;

  /* 音声(audio/)は生成後に内容が変わらないため、キャッシュ優先のままでよい
     (通信量を減らせる)。 */
  if(event.request.url.indexOf('/audio/') !== -1){
    event.respondWith(
      caches.match(event.request).then(function(cached){
        if(cached) return cached;
        return fetch(event.request).then(function(response){
          if(response && response.ok){
            var copy = response.clone();
            caches.open(CACHE_NAME).then(function(cache){ cache.put(event.request, copy); });
          }
          return response;
        });
      })
    );
    return;
  }

  /* index.html・JSON・アイコン等はネットワーク優先。
     オンラインなら常に最新版を取得し、取得できた分をキャッシュに保存し直す。
     オフライン時のみキャッシュにフォールバックする。 */
  event.respondWith(
    fetch(event.request).then(function(response){
      if(response && response.ok){
        var copy = response.clone();
        caches.open(CACHE_NAME).then(function(cache){ cache.put(event.request, copy); });
      }
      return response;
    }).catch(function(){
      return caches.match(event.request).then(function(cached){
        if(cached) return cached;
        if(event.request.mode === 'navigate') return caches.match('./index.html');
      });
    })
  );
});
