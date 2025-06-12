
---

## 2. Uploader les assets

1. **Add file → Upload files**  
2. Glisse tes captures (ex. `carte_crissements.png`, `demo.gif`) dans `docs/assets/`.  
3. Commit ; les images apparaîtront instantanément sur le site (grâce aux liens dans `index.md`).

---

## 3. (Optionnel) Navigation rapide entre pages

Le thème **jekyll-theme-minimal** n’a pas de barre de menu ; pour un mini-site c’est acceptable.  
Si tu veux un vrai header :

1. Crée `docs/_includes/header.html` avec quelques liens ;  
2. Ajoute dans `_config.yml` :

```yaml
include:
  - _includes
