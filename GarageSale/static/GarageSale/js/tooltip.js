/*--------------------------------------------------------
Short JS module to show nice tool-tips on django forms
--------------------------------------------------------*/

function showTooltip(e) {
    var parent = e.target.parentElement;
    var tooltip = parent.querySelector(".helptext");
    if (tooltip == null)
        return ;
    tooltip.style.left =
      (e.pageX + tooltip.clientWidth + 10 < document.body.clientWidth)
          ? (e.pageX + 10 + "px")
          : (document.body.clientWidth + 5 - tooltip.clientWidth + "px");
  tooltip.style.top =
      (e.pageY + tooltip.clientHeight + 10 < document.body.clientHeight)
          ? (e.pageY + 10 + "px")
          : (document.body.clientHeight + 5 - tooltip.clientHeight + "px");
}

function __document_loaded() {
    var tooltips = document.querySelectorAll("label");
    for(var i = 0; i < tooltips.length; i++) {
        let for_id = tooltips[i].htmlFor;
        let target = document.querySelector('[id="'+for_id+'"]');
        tooltips[i].addEventListener('mousemove', showTooltip);
        if (target)
            target.addEventListener('mousemove', showTooltip);

    }
}

document.addEventListener('DOMContentLoaded', __document_loaded);
