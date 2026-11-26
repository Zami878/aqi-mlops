document.querySelectorAll('.chart').forEach(function(box){
  var s=JSON.parse(box.dataset.series),svg=box.querySelector('svg'),hit=box.querySelector('.hit'),
      tip=box.querySelector('.tip'),xh=box.querySelector('.xh'),dots=box.querySelectorAll('.dot');
  var x0=+hit.dataset.x0,pw=+hit.dataset.pw,pt=+hit.dataset.pt,ph=+hit.dataset.ph,ym=+hit.dataset.ymax,n=s.d.length;
  function y(v){return pt+ph*(1-v/ym)}
  hit.addEventListener('mousemove',function(ev){
    var pt2=svg.createSVGPoint();pt2.x=ev.clientX;pt2.y=ev.clientY;
    var p=pt2.matrixTransform(svg.getScreenCTM().inverse());
    var i=Math.max(0,Math.min(n-1,Math.round((p.x-x0)/pw*(n-1)))),x=x0+pw*i/(n-1);
    xh.setAttribute('x1',x);xh.setAttribute('x2',x);
    dots[0].setAttribute('cx',x);dots[0].setAttribute('cy',y(s.a[i]));
    dots[1].setAttribute('cx',x);dots[1].setAttribute('cy',y(s.p[i]));
    var d=new Date(s.d[i]).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
    tip.innerHTML='<b>'+d+'</b><i style="background:var(--series-1)"></i>Observed '+s.a[i]+
      '<br><i style="background:var(--series-2)"></i>Forecast '+s.p[i]+
      '<br><span class="muted">Error '+(s.p[i]-s.a[i]).toFixed(1)+'</span>';
    tip.hidden=false;var r=box.getBoundingClientRect(),px=ev.clientX-r.left;
    tip.style.left=(px>r.width*0.65?px-tip.offsetWidth-14:px+14)+'px';tip.style.top='20px';
  });
  hit.addEventListener('mouseleave',function(){tip.hidden=true;xh.setAttribute('x1',-10);xh.setAttribute('x2',-10);
    dots.forEach(function(d){d.setAttribute('cx',-10)})});
});
