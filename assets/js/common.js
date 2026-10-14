$(document).ready(function() {
  // add toggle functionality to paper highlights buttons
  $('.abstract-toggle').click(function() {
    const $toggle = $(this);
    const $entry = $toggle.parent().parent();
    const isOpen = $entry.find(".abstract.hidden").toggleClass('open').hasClass('open');

    $toggle.toggleClass('open', isOpen);
    $toggle.attr('aria-expanded', isOpen);
    $toggle.attr('aria-label', isOpen ? 'Hide paper highlights' : 'Show paper highlights');
  });

  // expand and collapse additional research-use organizations
  $('.research-use-more-toggle').click(function() {
    const $toggle = $(this);
    const $links = $toggle.closest('.research-use-links');
    const isExpanded = !$links.hasClass('expanded');

    $links.toggleClass('expanded', isExpanded);
    $toggle.attr('aria-expanded', isExpanded);
    $toggle.find('.research-use-more-label').text(isExpanded ? 'Less' : 'More');
    $toggle.find('.research-use-more-count').text(isExpanded ? '' : `+${$toggle.data('more-count')}`);
  });

  // lazily load and expand the full citation-excerpt review
  $('.citation-excerpts-toggle').click(async function() {
    const $toggle = $(this);
    const $container = $toggle.closest('.citation-excerpts');
    const $panel = $container.find('.citation-excerpts-panel');
    const $list = $container.find('.citation-excerpts-list');
    const isExpanded = $toggle.attr('aria-expanded') === 'true';

    if (isExpanded) {
      $toggle.attr('aria-expanded', 'false');
      $panel.prop('hidden', true);
      return;
    }

    $toggle.attr('aria-expanded', 'true');
    $panel.prop('hidden', false);

    if ($container.data('loaded')) return;

    $container.addClass('is-loading');
    $list.text('Loading citation excerpts…');

    try {
      const response = await fetch($toggle.data('source'));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const payload = await response.json();
      const citations = payload[$container.data('citation-key')] || [];
      $list.empty();

      citations.forEach(function(citation) {
        const $link = $('<a>', {
          class: 'citation-excerpt',
          href: citation.url,
          target: '_blank',
          rel: 'noopener noreferrer',
          role: 'listitem'
        });
        const $heading = $('<span>', { class: 'citation-excerpt-heading' });
        $heading.append($('<span>', { class: 'citation-excerpt-title', text: citation.title }));
        if (citation.year) {
          $heading.append($('<span>', { class: 'citation-excerpt-year', text: citation.year }));
        }
        $link.append($heading);
        if (citation.authors) {
          $link.append($('<span>', { class: 'citation-excerpt-authors', text: citation.authors }));
        }
        $link.append($('<q>', { text: citation.excerpt }));
        const $footer = $('<span>', { class: 'citation-excerpt-footer' });
        $footer.append($('<span>', {
          class: 'citation-excerpt-source',
          text: citation.page ? `PDF page ${citation.page} · Open citing paper` : 'Open citing paper'
        }));
        if (Array.isArray(citation.organizations) && citation.organizations.length) {
          $footer.append($('<span>', {
            class: 'citation-excerpt-organizations',
            text: citation.organizations.join(' · ')
          }));
        }
        $link.append($footer);
        $list.append($link);
      });

      $container.data('loaded', true);
    } catch (error) {
      $list.text('Citation excerpts could not be loaded. Please try again.');
      $toggle.attr('aria-expanded', 'false');
    } finally {
      $container.removeClass('is-loading');
    }
  });

  $('a').removeClass('waves-effect waves-light');

  // bootstrap-toc
  if($('#toc-sidebar').length){
    var navSelector = "#toc-sidebar";
    var $myNav = $(navSelector);
    Toc.init($myNav);
    $("body").scrollspy({
      target: navSelector,
    });
  }

  // add css to jupyter notebooks
  const cssLink = document.createElement("link");
  cssLink.href  = "../css/jupyter.css";
  cssLink.rel   = "stylesheet";
  cssLink.type  = "text/css";

  let theme = localStorage.getItem("theme");
  if (theme == null || theme == "null") {
    const userPref = window.matchMedia;
    if (userPref && userPref("(prefers-color-scheme: dark)").matches) {
      theme = "dark";
    }
  }

  $('.jupyter-notebook-iframe-container iframe').each(function() {
    $(this).contents().find("head").append(cssLink);

    if (theme == "dark") {
      $(this).bind("load",function(){
        $(this).contents().find("body").attr({
          "data-jp-theme-light": "false",
          "data-jp-theme-name": "JupyterLab Dark"});
      });
    }
  });
});
