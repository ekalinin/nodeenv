.PHONY: default deploy deploy-github deploy-pypi clean env site
PYTHON=python3
TEST_ENV=env
DEV_TEST_ENV=env-dev

default:
	: do nothing when dpkg-buildpackage runs this project Makefile

deploy-github:
	git tag `grep "nodeenv_version =" nodeenv.py | grep -o -E '[0-9]\.[0-9]{1,2}\.[0-9]{1,2}'`
	git push --tags origin master

deploy-pypi:
	rm -rf dist
	@. ${DEV_TEST_ENV}/bin/activate && \
		pip install -U build twine && \
		$(PYTHON) -m build && \
		twine upload --repository pypi dist/*

deploy: contributors ut deploy-github deploy-pypi

clean:
	@rm -rf nodeenv.egg-info/
	@rm -rf dist/
	@rm -rf build/
	@rm -rf ${TEST_ENV}/

clean-test-env:
	@rm -rf ${TEST_ENV}

# https://virtualenv.pypa.io/en/legacy/reference.html#cmdoption-no-site-packages
# https://github.com/pypa/virtualenv/issues/1681
setup-test-env:
	@virtualenv ${TEST_ENV} > /dev/null 2>&1

env: clean-test-env setup-test-env
	@. ${TEST_ENV}/bin/activate                && \
		pip install .

# https://virtualenv.pypa.io/en/legacy/reference.html#cmdoption-no-site-packages
# https://github.com/pypa/virtualenv/issues/1681
env-dev:
	@rm -rf ${DEV_TEST_ENV}                           && \
		$(PYTHON) -m venv ${DEV_TEST_ENV}             && \
		. ${DEV_TEST_ENV}/bin/activate                && \
		pip install -r requirements-dev.txt

ut: env-dev
	@. ${DEV_TEST_ENV}/bin/activate && tox -e py314

coverage: env-dev
	@. ${DEV_TEST_ENV}/bin/activate && \
		coverage run -p -m pytest -m 'not integration' && \
		coverage report -m && \
		coverage html

# site/ with the changelog page rendered from CHANGES. rst2html5 comes
# from docutils and is taken from PATH, as CI has no env-dev. Single
# backticks in CHANGES mean code, so they are rendered as literals; the
# two lines added for that put the reported line numbers two ahead.
site:
	@rm -rf _site
	@cp -R site _site
	@(printf '.. default-role:: literal\n\n'; cat CHANGES) | \
		rst2html5 --halt=warning --no-raw --no-file-insertion \
		--template=site/changes.html - _site/changes.html

contributors:
	@echo "Nodeenv is written and maintained by Eugene Kalinin." > AUTHORS
	@echo "" >> AUTHORS
	@echo "Patches and Suggestions" >> AUTHORS
	@echo '```````````````````````' >> AUTHORS
	@echo "" >> AUTHORS
	@git log --raw | grep "^Author: " | \
		sort | uniq -c | sort -n -r | \
		cut -d ':' -f 2 | sed 's/^/- /' | \
		cut -d '<' -f1 | uniq | grep -v Kalinin | sed 's/ *$$//g' >> AUTHORS
