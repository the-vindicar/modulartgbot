function onLoad(){
    'use strict';
    const anchor = decodeURIComponent(window.location.hash.substring(1));
    if (!anchor) return;
    const cells = document.querySelectorAll('th, td');
    for (let i = 0; i < cells.length; i++)
    {
        const colname = cells[i].getAttribute('data-name');
        if (colname == anchor)
            cells[i].className += ' active'
    }
}
window.addEventListener('DOMContentLoaded', onLoad);