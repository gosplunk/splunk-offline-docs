require([
    'jquery',
    'splunkjs/mvc/simplexml/ready!',
    'splunk.util'
], function ($, _, utils) {
    'use strict';

    var frameUrl = utils.make_url('/static/app/splunk_offline_docs/index.html?v=3');
    var $target = $('.dashboard-body').first();

    if (!$target.length) {
        $target = $('.main-section-body').first();
    }

    $target.empty().css({
        padding: 0,
        margin: 0
    });

    $('<iframe/>', {
        src: frameUrl,
        title: 'Splunk Offline Docs',
        class: 'offline-docs-frame',
        css: {
            width: '100%',
            minHeight: 'calc(100vh - 120px)',
            border: 0,
            display: 'block',
            background: '#fff'
        }
    }).appendTo($target);
});
