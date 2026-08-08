/* Click-to-sort for every plain article table (Material's documented
   tablesort integration — see the shared docs style guide). */
document$.subscribe(function () {
  var tables = document.querySelectorAll("article table:not([class])")
  tables.forEach(function (table) {
    new Tablesort(table)
  })
})
