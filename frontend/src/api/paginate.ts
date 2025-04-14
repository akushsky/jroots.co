export function getPaginationPages(current: number, totalPages: number, delta: number = 1) {
    const pages: (number | 'ellipsis')[] = [];

    for (let i = 0; i < totalPages; i++) {
        if (
            i === 0 ||                                 // always show first
            i === totalPages - 1 ||                    // always show last
            Math.abs(i - current) <= delta             // show nearby pages
        ) {
            pages.push(i);
        } else if (pages[pages.length - 1] !== 'ellipsis') {
            pages.push('ellipsis');
        }
    }

    return pages;
}
