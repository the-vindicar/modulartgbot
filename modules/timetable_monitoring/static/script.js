function onLoad(){
    'use strict';
    document.querySelectorAll('.active').forEach((item) => {
        item.className = item.className.replace(/\bactive\b/);
    });

    const anchor = decodeURIComponent(window.location.hash.substring(1));
    if (!anchor) return;
    document.querySelectorAll('th, td').forEach((cell) => {
        const colname = cell.getAttribute('data-name');
        if (colname == anchor)
            cell.className += ' active'
    });
}
window.addEventListener('DOMContentLoaded', onLoad);
window.addEventListener('hashchange', onLoad);