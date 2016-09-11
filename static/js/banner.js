banners = [
'https://i.imgur.com/7xoyXNi.png',
'https://i.imgur.com/9snwgBB.png',
'https://i.imgur.com/JEHCad1.png',
'https://i.imgur.com/ZuywHbC.png',
'https://i.imgur.com/BkqEvW4.gif',
'https://i.imgur.com/I6F2msY.png'
];

function getRandomBannerImage(){
    return banners[Math.floor(Math.random() * banners.length)];
}

