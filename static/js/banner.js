banners = [
'http://i.imgur.com/7xoyXNi.png',
'http://i.imgur.com/9snwgBB.png',
'http://i.imgur.com/JEHCad1.png',
'http://i.imgur.com/ZuywHbC.png',
'http://i.imgur.com/BkqEvW4.gif',
'http://i.imgur.com/I6F2msY.png'
];

function getRandomBannerImage(){
    return banners[Math.floor(Math.random() * banners.length)];
}
