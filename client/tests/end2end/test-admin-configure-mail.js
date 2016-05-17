describe('adming configure mail', function() {
  it('should configure mail', function(done) {
    browser.setLocation('admin/mail');

    expect(element(by.model('admin.notification.tip_expiration_threshold')).getAttribute('value')).toEqual('72');

    element(by.model('admin.notification.tip_expiration_threshold')).clear().sendKeys('24');

    // save settings
    element(by.css('[data-ng-click="Utils.update(admin.notification)"]')).click().then(function() {
      browser.setLocation('admin/landing');
      browser.setLocation('admin/mail');
      expect(element(by.model('admin.notification.tip_expiration_threshold')).getAttribute('value')).toEqual('24');
      done();
    });
  });
});