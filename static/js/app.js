// Lazy loading fallback for browsers that don't support loading="lazy"
(function () {
    if ("loading" in HTMLImageElement.prototype) return;

    var images = document.querySelectorAll('img[loading="lazy"]');
    if (!images.length) return;

    if ("IntersectionObserver" in window) {
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    var img = entry.target;
                    img.src = img.dataset.src || img.src;
                    observer.unobserve(img);
                }
            });
        }, { rootMargin: "200px" });

        images.forEach(function (img) { observer.observe(img); });
    }
})();
