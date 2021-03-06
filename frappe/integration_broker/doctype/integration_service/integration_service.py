# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.background_jobs import enqueue, get_jobs
import json, urlparse
from frappe.utils import get_request_session

class IntegrationService(Document):
	def on_update(self):
		if self.enabled:
			if not self.flags.ignore_mandatory:
				self.enable_service()
				self.install_fixtures()

	def install_fixtures(self):
		pass

	def enable_service(self):
		service_doc = "{0} Settings".format(self.service)
		frappe.get_doc(service_doc).enable()

	#rest request handler
	def get_request(self, url, auth=None, data=None):
		if not auth:
			auth = ''
		if not data:
			data = {}

		try:
			s = get_request_session()
			frappe.flags.integration_request = s.get(url, data={}, auth=auth)
			frappe.flags.integration_request.raise_for_status()
			return frappe.flags.integration_request.json()

		except Exception, exc:
			frappe.log_error(frappe.get_traceback())
			raise exc

	def post_request(self, url, auth=None, data=None):
		if not auth:
			auth = ''
		if not data:
			data = {}
		try:
			s = get_request_session()
			res = s.post(url, data=data, auth=auth)
			res.raise_for_status()

			if res.headers.get("content-type") == "text/plain; charset=utf-8":
				return urlparse.parse_qs(res.text)

			return res.json()
		except Exception, exc:
			frappe.log_error()
			raise exc

	def put_request(url, auth=None, data=None):
		pass

	def create_request(self, data, integration_type, service_name, name=None):
		if not isinstance(data, basestring):
			data = json.dumps(data)

		integration_request = frappe.get_doc({
			"doctype": "Integration Request",
			"integration_type": integration_type,
			"integration_request_service": service_name,
			"data": data
		})

		if name:
			integration_request.flags._name = name

		integration_request.insert(ignore_permissions=True)
		frappe.db.commit()

		return integration_request

def get_integration_controller(service_name):
	'''Returns integration controller module from app_name.integrations.{service}'''
	try:
		return frappe.get_doc("{0} Settings".format(service_name))
	except Exception:
		frappe.throw(_("Module {service} not found".format(service=service_name)))

@frappe.whitelist()
def get_integration_services():
	services = [""]
	for app in frappe.get_installed_apps():
		services.extend(frappe.get_hooks("integration_services", app_name = app))

	return services

def trigger_integration_service_events():
	for service in frappe.get_all("Integration Service", filters={"enabled": 1}, fields=["name"]):
		controller = get_integration_controller(service.name)

		if hasattr(controller, "scheduled_jobs"):
			for job in controller.scheduled_jobs:
				for event, handlers in job.items():
					for handler in handlers:
						if handler not in get_jobs():
							enqueue(handler, queue='short', event=event)